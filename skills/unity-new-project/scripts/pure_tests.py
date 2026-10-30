#!/usr/bin/env python3
"""Run a Unity project's PURE tests without opening Unity: seconds, no lane, no lock.

A "pure" assembly is an asmdef with "noEngineReferences": true. This compiles every pure asmdef
as its own assembly, named exactly as the asmdef (so InternalsVisibleTo and `internal` behave as
they do in the Editor; one merged assembly would let a test see internals the Editor refuses),
then compiles the test folder's files that touch nothing but those assemblies, and runs them with
NUnit's own runner (NUnitTestAssemblyRunner, the API Unity's test framework drives), so
[TestCase] / [Values] / [TestCaseSource] expand exactly as NUnit expands them.

Every tool comes from the installed Editor and the project's own package cache; nothing is
downloaded:
  dotnet  <Editor>/Scripting/NetCoreRuntime/dotnet          (the .NET runtime the Editor ships)
  csc     <Editor>/Scripting/DotNetSdkRoslyn/csc.dll        (run by that dotnet, -langversion:9.0)
  NUnit   Library/PackageCache/com.unity.ext.nunit@*/net40/unity-custom/nunit.framework.dll
The Editor version is read from ProjectSettings/ProjectVersion.txt.

A test file is EXCLUDED, and printed with its reason, when its code (comments stripped) names
UnityEngine or UnityEditor, has a `using` for a namespace no pure assembly declares (other than
System* and NUnit*), matches --exclude REGEX, or uses a type declared in an excluded file. Those
tests run only in the Editor leg, which stays the verdict that counts.

This is CoreCLR, not Mono: maths library results can differ in the last bits, so a test with a
tolerance tighter than that is the Editor's to judge.

  pure_tests.py run  --project P --tests Assets/Tests/Rules [--filter TEXT] [--exclude REGEX]
                     [--out DIR] [--scripting DIR] [--env K=V ...] [--keep]
  pure_tests.py plan --project P --tests DIR      (what would compile and what is excluded; no tools)
  pure_tests.py selftest [--e2e PROJECT]          (classification; with --e2e, a synthetic suite is
                                                   compiled and run with PROJECT's Editor and NUnit)

Exit: 0 all green · 2 a test failed or was inconclusive · 3 harness failure: no Editor or
package cache, a pure asmdef that references an engine one, a compile error, or zero tests ran
· 1 a usage error (a bad flag or a missing argument). A compile error is never worked around by excluding the file.
Stdlib only.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ENGINE_TOKEN = re.compile(r'\bUnityEngine\b|\bUnityEditor\b')
USING = re.compile(r'^\s*(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?([A-Za-z_][\w.]*)\s*;', re.M)
NAMESPACE = re.compile(r'\bnamespace\s+([A-Za-z_][\w.]*)')
DECLARED = re.compile(r'\b(?:class|struct|enum|interface|record)\s+([A-Za-z_]\w*)')
# `where T : class where U : ...` and `new()` constraints put keywords after `class`/`struct`.
KEYWORDS = {'where', 'new', 'in', 'out', 'ref', 'class', 'struct', 'unmanaged', 'notnull', 'default'}


class HarnessError(Exception):
    pass


def strip_comments(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)


def read_code(path):
    with open(path, encoding='utf-8-sig') as f:
        return strip_comments(f.read())


def load_asmdefs(project):
    """name -> {dir, refs, pure, unsafe, guid} for every asmdef under Assets/."""
    out = {}
    for path in sorted(glob.glob(os.path.join(project, 'Assets', '**', '*.asmdef'), recursive=True)):
        with open(path, encoding='utf-8-sig') as f:
            d = json.load(f)
        guid = None
        meta = path + '.meta'
        if os.path.exists(meta):
            m = re.search(r'^guid:\s*(\w+)', open(meta, encoding='utf-8').read(), re.M)
            guid = m.group(1) if m else None
        out[d['name']] = {
            'dir': os.path.dirname(path),
            'refs': list(d.get('references', [])),
            'pure': bool(d.get('noEngineReferences', False)),
            'unsafe': bool(d.get('allowUnsafeCode', False)),
            'guid': guid,
        }
    return out


def resolve_ref(ref, asmdefs):
    if ref.startswith('GUID:'):
        g = ref[5:]
        for name, a in asmdefs.items():
            if a['guid'] == g:
                return name
        return None
    return ref if ref in asmdefs else None


def pure_order(asmdefs):
    """Pure asmdefs in dependency order, each with its resolved pure references."""
    pure = {n for n, a in asmdefs.items() if a['pure']}
    deps = {}
    for n in sorted(pure):
        deps[n] = []
        for r in asmdefs[n]['refs']:
            rn = resolve_ref(r, asmdefs)
            if rn is None:
                raise HarnessError('%s references %s, which is not an asmdef under Assets/' % (n, r))
            if rn not in pure:
                raise HarnessError('%s is noEngineReferences but references %s, which is not' % (n, rn))
            deps[n].append(rn)
    order, state = [], {}

    def visit(n):
        if state.get(n) == 1:
            raise HarnessError('reference cycle through ' + n)
        if state.get(n) == 2:
            return
        state[n] = 1
        for d in deps[n]:
            visit(d)
        state[n] = 2
        order.append(n)
    for n in sorted(pure):
        visit(n)
    return order, deps


def sources(root, stop_at_asmdef=True):
    """Unity's rule: an asmdef's folder minus every subtree that holds another asmdef."""
    found = []
    for d, dirs, files in os.walk(root):
        dirs.sort()
        if stop_at_asmdef and d != root and any(f.endswith('.asmdef') for f in files):
            dirs[:] = []
            continue
        found += [os.path.join(d, f) for f in sorted(files) if f.endswith('.cs')]
    return found


def namespace_allowed(ns, pure_namespaces):
    root = ns.split('.')[0]
    if root in ('System', 'NUnit'):
        return True
    for p in pure_namespaces:
        if p == ns or p.startswith(ns + '.'):
            return True
    return False


def classify_tests(test_files, pure_namespaces, extra_exclude=None):
    """(included, {excluded_file: reason}) with the transitive closure over declared types."""
    code = {t: read_code(t) for t in test_files}
    extra = re.compile(extra_exclude) if extra_exclude else None
    why = {}
    for t in test_files:
        m = ENGINE_TOKEN.search(code[t])
        if m:
            why[t] = 'touches ' + m.group(0)
            continue
        bad = [u for u in USING.findall(code[t]) if not namespace_allowed(u, pure_namespaces)]
        if bad:
            why[t] = 'using ' + bad[0]
            continue
        if extra and extra.search(code[t]):
            why[t] = 'matches --exclude'
    changed = True
    while changed:
        changed = False
        names = {}
        for x in why:
            for n in DECLARED.findall(code[x]):
                if n not in KEYWORDS:
                    names[n] = x
        for t in test_files:
            if t in why:
                continue
            for n, x in names.items():
                if re.search(r'\b' + re.escape(n) + r'\b', code[t]):
                    why[t] = 'uses %s declared in %s' % (n, os.path.basename(x))
                    changed = True
                    break
    return [t for t in test_files if t not in why], why


def make_plan(project, tests_dir, extra_exclude=None):
    asmdefs = load_asmdefs(project)
    order, deps = pure_order(asmdefs)
    if not order:
        raise HarnessError('no asmdef under Assets/ has "noEngineReferences": true')
    units = []
    pure_ns = set()
    for n in order:
        files = sources(asmdefs[n]['dir'])
        if not files:
            raise HarnessError(n + ': no sources')
        for f in files:
            pure_ns.update(NAMESPACE.findall(read_code(f)))
        units.append({'name': n, 'files': files, 'deps': deps[n], 'unsafe': asmdefs[n]['unsafe']})
    tdir = os.path.join(project, tests_dir)
    if not os.path.isdir(tdir):
        raise HarnessError('no tests folder ' + tdir)
    test_name = 'PureTests'
    for name, a in asmdefs.items():
        if os.path.normpath(a['dir']) == os.path.normpath(tdir):
            test_name = name
    if test_name in order:
        raise HarnessError(test_name + ' is pure itself; point --tests at a folder of tests')
    test_files = sources(tdir)
    test_ns = set()
    for f in test_files:  # the tests' own namespaces (helpers in a sibling file) are not foreign
        test_ns.update(NAMESPACE.findall(read_code(f)))
    included, why = classify_tests(test_files, pure_ns | test_ns, extra_exclude)
    return {'units': units, 'test_name': test_name, 'tests': included, 'excluded': why}


def find_tools(project, scripting=None):
    if not scripting:
        vt = os.path.join(project, 'ProjectSettings', 'ProjectVersion.txt')
        if not os.path.exists(vt):
            raise HarnessError('not a Unity project: ' + project)
        m = re.search(r'^m_EditorVersion:\s*(\S+)', open(vt).read(), re.M)
        ver = m.group(1)
        scripting = os.environ.get('UNITY_SCRIPTING') or (
            '/Applications/Unity/Hub/Editor/%s/Unity.app/Contents/Resources/Scripting' % ver
            if sys.platform == 'darwin' else
            os.path.expanduser('~/Unity/Hub/Editor/%s/Editor/Data' % ver))
    dotnet = os.path.join(scripting, 'NetCoreRuntime', 'dotnet')
    csc = os.path.join(scripting, 'DotNetSdkRoslyn', 'csc.dll')
    if not (os.access(dotnet, os.X_OK) and os.path.exists(csc)):
        raise HarnessError('bundled dotnet/csc not found under %s (pass --scripting)' % scripting)
    fw = sorted(glob.glob(os.path.join(scripting, 'NetCoreRuntime', 'shared', 'Microsoft.NETCore.App', '*')),
                key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r'[.-]', os.path.basename(p))])
    if not fw:
        raise HarnessError('no Microsoft.NETCore.App under ' + scripting)
    hits = glob.glob(os.path.join(project, 'Library', 'PackageCache', 'com.unity.ext.nunit@*'))
    if len(hits) != 1:
        raise HarnessError('%d copies of com.unity.ext.nunit in Library/PackageCache (open the project '
                           'in Unity once; two means a stale cache)' % len(hits))
    nunit = os.path.join(hits[0], 'net40', 'unity-custom', 'nunit.framework.dll')
    if not os.path.exists(nunit):
        raise HarnessError('no nunit.framework.dll at ' + nunit)
    return {'dotnet': dotnet, 'csc': csc, 'fw': fw[-1], 'fwver': os.path.basename(fw[-1]), 'nunit': nunit}


RUNNER = r'''
using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework.Api;
using NUnit.Framework.Interfaces;
using NUnit.Framework.Internal;

// Every LEAF result is counted. A suite that failed with no failing leaf under it (a fixture
// set-up, a TestCaseSource that threw) counts as a failure: a fixture that never ran its tests
// reports zero failures, and that is the most convincing green there is.
static class Runner
{
    static int Main(string[] args)
    {
        var runner = new NUnitTestAssemblyRunner(new DefaultTestAssemblyBuilder());
        runner.Load(Assembly.LoadFrom(args[0]), new Dictionary<string, object>());
        ITestFilter filter = args.Length > 1 && args[1].Length > 0 ? new Contains(args[1]) : TestFilter.Empty;
        ITestResult root = runner.Run(new Listener(), filter);
        var n = new Dictionary<TestStatus, int>();
        int suiteErrors = 0;
        Walk(root, n, ref suiteErrors);
        int Get(TestStatus s) => n.TryGetValue(s, out int v) ? v : 0;
        int passed = Get(TestStatus.Passed), failed = Get(TestStatus.Failed) + suiteErrors,
            inconclusive = Get(TestStatus.Inconclusive), skipped = Get(TestStatus.Skipped);
        int total = passed + failed + inconclusive + skipped;
        Console.WriteLine($"VERDICT total={total} passed={passed} failed={failed} inconclusive={inconclusive} skipped={skipped}");
        return total == 0 ? 3 : failed > 0 || inconclusive > 0 ? 2 : 0;
    }

    static int Walk(ITestResult r, Dictionary<TestStatus, int> n, ref int suiteErrors)
    {
        if (!r.Test.IsSuite)
        {
            TestStatus st = r.ResultState.Status;
            n.TryGetValue(st, out int c);
            n[st] = c + 1;
            // Printed from the result tree after the run: NUnit captures Console.Out while tests run.
            if (st == TestStatus.Failed || st == TestStatus.Inconclusive)
                Console.WriteLine("  x " + st.ToString().ToUpperInvariant() + " " + r.FullName
                                  + "\n      " + (r.Message ?? "").Replace("\n", "\n      ").TrimEnd());
            return st == TestStatus.Failed ? 1 : 0;
        }
        int failedBelow = 0;
        foreach (ITestResult child in r.Children) failedBelow += Walk(child, n, ref suiteErrors);
        if (r.ResultState.Status == TestStatus.Failed && failedBelow == 0 && r.ResultState.Site != FailureSite.Child)
        {
            suiteErrors++;
            Console.WriteLine("  x SUITE " + r.FullName + ": " + r.Message);
        }
        return failedBelow;
    }

    sealed class Listener : ITestListener
    {
        public void TestStarted(ITest test) { }
        public void TestFinished(ITestResult r) { }
        public void TestOutput(TestOutput output) { }
    }

    sealed class Contains : TestFilter
    {
        readonly string text;
        public Contains(string text) { this.text = text; }
        public override bool Match(ITest test) => !test.IsSuite && test.FullName.Contains(text);
        public override TNode AddToXml(TNode parentNode, bool recursive) => parentNode.AddElement("contains", text);
    }
}
'''


def compile_unit(tools, out, name, kind, files, refs, unsafe=False):
    fw_refs = ['-r:' + p for p in sorted(glob.glob(os.path.join(tools['fw'], '*.dll')))]
    rsp = os.path.join(out, name + '.rsp')
    args = ['-nologo', '-noconfig', '-langversion:9.0', '-nullable:disable', '-warn:0', '-deterministic',
            '-target:' + kind, '-out:' + os.path.join(out, name + '.dll')] + fw_refs + ['-r:' + r for r in refs]
    if unsafe:
        args.append('-unsafe')
    with open(rsp, 'w') as f:  # a response file: hundreds of sources overflow argv
        f.write('\n'.join('"%s"' % a if ' ' in a else a for a in args + files) + '\n')
    log = os.path.join(out, name + '.csc.log')
    with open(log, 'w') as f:
        rc = subprocess.call([tools['dotnet'], tools['csc'], '@' + rsp], stdout=f, stderr=subprocess.STDOUT)
    if rc != 0:
        errs = sorted({l.strip() for l in open(log) if 'error CS' in l})[:30]
        raise HarnessError('%s did not compile (log %s):\n    %s' % (name, log, '\n    '.join(errs)))
    return os.path.join(out, name + '.dll')


def run(project, plan, tools, out, filt, say=print, extra_env=None):
    if os.path.exists(out):
        shutil.rmtree(out)  # a dll left from the last run would be a stale verdict in binary form
    os.makedirs(out)
    shutil.copy(tools['nunit'], out)
    built = {}
    for u in plan['units']:
        built[u['name']] = compile_unit(tools, out, u['name'], 'library', u['files'],
                                        [built[d] for d in u['deps']], u['unsafe'])
    if not plan['tests']:
        raise HarnessError('no test file is pure; nothing to run')
    tests_dll = compile_unit(tools, out, plan['test_name'], 'library', plan['tests'],
                             list(built.values()) + [tools['nunit']])
    rpath = os.path.join(out, 'Runner.cs')
    with open(rpath, 'w') as f:
        f.write(RUNNER)
    runner = compile_unit(tools, out, 'pure-tests-runner', 'exe', [rpath], [tools['nunit']])
    with open(os.path.join(out, 'pure-tests-runner.runtimeconfig.json'), 'w') as f:
        json.dump({'runtimeOptions': {'tfm': 'net%s.0' % tools['fwver'].split('.')[0], 'framework': {
            'name': 'Microsoft.NETCore.App', 'version': tools['fwver']}}}, f)
    # The working directory is the project root, as in the Editor, so a test that finds files
    # relative to the project behaves the same in both legs.
    env = dict(os.environ, **(extra_env or {}))
    p = subprocess.run([tools['dotnet'], runner, tests_dll, filt or ''], cwd=project, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with open(os.path.join(out, 'run.log'), 'w') as f:
        f.write(p.stdout)
    sys.stdout.write(p.stdout)
    verdict = [l for l in p.stdout.splitlines() if l.startswith('VERDICT ')]
    if not verdict:
        return 3, None
    counts = dict(kv.split('=') for kv in verdict[-1].split()[1:])
    return (p.returncode if p.returncode in (0, 2, 3) else 3), {k: int(v) for k, v in counts.items()}


def print_plan(project, plan, say=print):
    for u in plan['units']:
        say('  %-36s %3d files  refs: %s' % (u['name'], len(u['files']), ', '.join(u['deps']) or '-'))
    say('  %-36s %3d files compiled, %d excluded (Editor leg only):'
        % (plan['test_name'], len(plan['tests']), len(plan['excluded'])))
    for t in sorted(plan['excluded']):
        say('    - %s  %s' % (os.path.relpath(t, project), plan['excluded'][t]))


# ── selftest ─────────────────────────────────────────────────────────────────────────────────

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def fake_project(root):
    write(os.path.join(root, 'ProjectSettings', 'ProjectVersion.txt'), 'm_EditorVersion: 6000.0.0f1\n')
    write(os.path.join(root, 'Assets/Scripts/Rules/Game.Rules.asmdef'),
          json.dumps({'name': 'Game.Rules', 'noEngineReferences': True}))
    write(os.path.join(root, 'Assets/Scripts/Rules/Game.Rules.asmdef.meta'), 'guid: aaaa1111\n')
    write(os.path.join(root, 'Assets/Scripts/Rules/Score.cs'),
          '[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("Game.Tests")]\n'
          'namespace Game.Rules { public static class Score {\n'
          '  public static int Add(int a, int b) => a + b;\n'
          '  internal static int Secret() => 7; } }\n')
    write(os.path.join(root, 'Assets/Scripts/Rules/Sub/Game.Rules.Sub.asmdef'),
          json.dumps({'name': 'Game.Rules.Sub', 'noEngineReferences': True, 'references': ['GUID:aaaa1111']}))
    write(os.path.join(root, 'Assets/Scripts/Rules/Sub/Twice.cs'),
          'namespace Game.Rules.Sub { public static class Twice { public static int Of(int x) => Game.Rules.Score.Add(x, x); } }\n')
    write(os.path.join(root, 'Assets/Scripts/Runtime/Game.Runtime.asmdef'), json.dumps({'name': 'Game.Runtime'}))
    write(os.path.join(root, 'Assets/Scripts/Runtime/View.cs'), 'using UnityEngine;\nnamespace Game.View { class V {} }\n')
    t = os.path.join(root, 'Assets/Tests/Rules')
    write(os.path.join(t, 'Game.Tests.asmdef'), json.dumps({'name': 'Game.Tests', 'references': ['Game.Rules']}))
    write(os.path.join(t, 'ScoreTests.cs'),
          '// UnityEngine is only mentioned in a comment\nusing NUnit.Framework;\nusing Game.Rules;\nusing Game.Rules.Sub;\n'
          'namespace Game.Tests { public class ScoreTests {\n'
          '  [TestCase(1, 2, 3)] [TestCase(2, 2, 4)] public void Adds(int a, int b, int s) => Assert.AreEqual(s, Score.Add(a, b));\n'
          '  [Test] public void SeesInternals() => Assert.AreEqual(7, Score.Secret());\n'
          '  [Test] public void Twice() => Assert.AreEqual(6, Game.Rules.Sub.Twice.Of(3));\n'
          '  [Test] public void Fails() => Assert.AreEqual(1, 2, "deliberate"); } }\n')
    write(os.path.join(t, 'SceneFixture.cs'),
          'using UnityEngine;\nnamespace Game.Tests { public class SceneFixture<T> where T : class { } }\n')
    write(os.path.join(t, 'Helpers.cs'),
          'namespace Game.Tests.Helpers { public static class H { public static int One => 1; } }\n')
    write(os.path.join(t, 'HelperTests.cs'),
          'using NUnit.Framework;\nusing Game.Tests.Helpers;\nusing System.Linq;\n'
          'namespace Game.Tests { public class HelperTests { [Test] public void One() =>\n'
          '  Assert.AreEqual(1, new[] { H.One }.Where(x => x > 0).Count()); } }\n')
    write(os.path.join(t, 'UsesFixture.cs'),
          'using NUnit.Framework;\nnamespace Game.Tests { public class UsesFixture { [Test] public void T() { new SceneFixture<string>(); } } }\n')
    write(os.path.join(t, 'RuntimeTests.cs'),
          'using NUnit.Framework;\nusing Game.View;\nnamespace Game.Tests { public class RuntimeTests { } }\n')


def selftest(e2e_project=None):
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(('  ok   ' if cond else '  FAIL ') + msg)
        ok = ok and cond

    tmp = tempfile.mkdtemp(prefix='pure_tests_selftest_')
    try:
        fake_project(tmp)
        plan = make_plan(tmp, 'Assets/Tests/Rules')
        names = [u['name'] for u in plan['units']]
        check(names == ['Game.Rules', 'Game.Rules.Sub'], 'pure asmdefs in dependency order: %s' % names)
        check(plan['units'][1]['deps'] == ['Game.Rules'], 'a GUID: reference resolves through the .meta')
        rules_files = [os.path.basename(f) for f in plan['units'][0]['files']]
        check(rules_files == ['Score.cs'], 'a nested asmdef subtree is not compiled into its parent: %s' % rules_files)
        check(plan['test_name'] == 'Game.Tests', 'the test assembly keeps its asmdef name (InternalsVisibleTo)')
        inc = sorted(os.path.basename(t) for t in plan['tests'])
        exc = {os.path.basename(k): v for k, v in plan['excluded'].items()}
        check(inc == ['HelperTests.cs', 'Helpers.cs', 'ScoreTests.cs'],
              'pure test files and their own helper namespace are compiled: %s' % inc)
        check('HelperTests.cs' in inc, 'a LINQ `where` is not mistaken for a type an excluded file declares')
        check(exc.get('SceneFixture.cs') == 'touches UnityEngine', 'an engine file is excluded with its reason')
        check(exc.get('RuntimeTests.cs') == 'using Game.View', 'a using of a non-pure namespace is excluded')
        check(exc.get('UsesFixture.cs', '').startswith('uses SceneFixture'), 'the closure excludes a file using an excluded type')
        check(namespace_allowed('Game', {'Game.Rules'}), 'a parent namespace of a pure one is allowed')
        check(not namespace_allowed('Gam', {'Game.Rules'}), 'a prefix that is not a namespace boundary is not')
        write(os.path.join(tmp, 'Assets/Scripts/Rules/Bad/Game.Bad.asmdef'),
              json.dumps({'name': 'Game.Bad', 'noEngineReferences': True, 'references': ['Game.Runtime']}))
        try:
            make_plan(tmp, 'Assets/Tests/Rules')
            check(False, 'a pure asmdef referencing an engine asmdef is refused')
        except HarnessError as e:
            check('Game.Runtime' in str(e), 'a pure asmdef referencing an engine asmdef is refused')
        shutil.rmtree(os.path.join(tmp, 'Assets/Scripts/Rules/Bad'))

        if e2e_project:
            tools = find_tools(e2e_project)
            tools_proj = dict(tools)
            out = os.path.join(tmp, 'out')
            t0 = time.time()
            rc, counts = run(tmp, make_plan(tmp, 'Assets/Tests/Rules'), tools_proj, out, None, say=lambda *_: None)
            check(rc == 2, 'e2e: a failing test exits 2 (got %s)' % rc)
            check(counts == {'total': 6, 'passed': 5, 'failed': 1, 'inconclusive': 0, 'skipped': 0},
                  'e2e: [TestCase] expands, internals are visible, counts %s' % counts)
            rc, counts = run(tmp, make_plan(tmp, 'Assets/Tests/Rules'), tools_proj, out, 'Adds', say=lambda *_: None)
            check(rc == 0 and counts and counts['total'] == 2, 'e2e: --filter narrows to the two cases (rc %s, %s)' % (rc, counts))
            rc, counts = run(tmp, make_plan(tmp, 'Assets/Tests/Rules'), tools_proj, out, 'NoSuchTest', say=lambda *_: None)
            check(rc == 3, 'e2e: a filter that matches nothing is a harness failure, not green (rc %s)' % rc)
            print('  e2e took %.1f s' % (time.time() - t0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('selftest ' + ('passed' if ok else 'FAILED'))
    return 0 if ok else 1


class UsageParser(argparse.ArgumentParser):
    """Usage errors exit 1 (refused), never 2: here 2 is a verdict."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv):
    ap = UsageParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('run', 'plan'):
        p = sub.add_parser(name)
        p.add_argument('--project', default='.')
        p.add_argument('--tests', required=True, help='test folder, relative to the project')
        p.add_argument('--exclude', help='regex: also exclude test files whose code matches')
        if name == 'run':
            p.add_argument('--filter', help='run only tests whose full name contains this')
            p.add_argument('--out', help='output folder (default: a fresh temp folder per run)')
            p.add_argument('--scripting', help="the Editor's Scripting folder, if not the Hub default")
            p.add_argument('--keep', action='store_true', help='keep the output folder')
            p.add_argument('--env', action='append', default=[], metavar='K=V',
                           help='set an environment variable for the test process (repeatable)')
    s = sub.add_parser('selftest')
    s.add_argument('--e2e', metavar='PROJECT', help='also compile and run a synthetic suite with this project\'s tools')
    a = ap.parse_args(['selftest', *argv[1:]] if argv[:1] == ['--selftest'] else argv)
    if a.cmd == 'selftest':
        try:
            return selftest(a.e2e)
        except HarnessError as e:
            print('selftest harness failure: %s' % e)
            return 3
    project = os.path.abspath(a.project)
    try:
        plan = make_plan(project, a.tests, a.exclude)
        print('> pure tests: %s' % project)
        print_plan(project, plan)
        if a.cmd == 'plan':
            return 0
        t0 = time.time()
        tools = find_tools(project, a.scripting)
        print('  dotnet %s, NUnit %s' % (tools['fwver'], os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(tools['nunit']))))))
        out = a.out or tempfile.mkdtemp(prefix='pure_tests_')  # one folder per run: agents run in parallel
        env = dict(kv.split('=', 1) for kv in a.env)
        rc, _ = run(project, plan, tools, out, a.filter, extra_env=env)
    except HarnessError as e:
        print('  x harness failure: %s' % e, file=sys.stderr)
        return 3
    print('  %.1f s, output in %s' % (time.time() - t0, out))
    print({0: '  green (excluded files above are the Editor leg\'s)', 2: '  tests failed: a real verdict'}
          .get(rc, '  harness failure: nothing was verified'))
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
