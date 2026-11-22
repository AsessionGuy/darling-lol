"""Issue #299 A/B switches: INDIUM_AB letters turn single Indium changes off for an NVIDIA frame-rate bisect."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/metal--deps--indium.patch'


def section(name):
    patch = PATCH.read_text()
    marker = f'diff --git a/{name} b/{name}\n'
    return patch.split(marker, 1)[1].split('\ndiff --git ', 1)[0]


def added(name):
    """The patched file's text as far as the hunks show it: added and context lines."""
    lines = section(name).splitlines()
    return ''.join(line[1:] + '\n' for line in lines
                   if line[:1] in ('+', ' ') and not line.startswith('+++'))


def function(text, signature):
    return text.split(signature, 1)[1].split('\n};\n', 1)[0]


PROGRAM = r'''
#include <indium/ab-switch.private.hpp>
#include <cstdio>
int main() {
    std::printf("%d%d%d%d%d\n", Indium::AB::off('s'), Indium::AB::off('t'), Indium::AB::off('b'), Indium::AB::off('d'),
        Indium::AB::off('s'));
    return 0;
}
'''


class ABSwitchSites(unittest.TestCase):
    def test_binary_retirement_switch_destroys_before_retiring(self):
        body = function(added('src/indium/device.cpp'), 'void Indium::PrivateDevice::putBinarySemaphore(')
        switch = body.index("Indium::AB::off('s')")
        self.assertLess(switch, body.index('entry->pending.push_back'))
        self.assertIn('retirement.unwaited.erase(semaphore.semaphore)', body[switch:body.index('entry->pending.push_back')])

    def test_timeline_retirement_switch_destroys_before_retiring(self):
        body = function(added('src/indium/device.cpp'), 'void Indium::PrivateDevice::putTimelineSemaphore(')
        self.assertLess(body.index("Indium::AB::off('t')"), body.index('retireTimelineSemaphore('))
        # the pool still keeps what it can: the switch only replaces the retirement path
        self.assertLess(body.index('_availableTimelineSemaphores.emplace_back'), body.index("Indium::AB::off('t')"))

    def test_every_blit_keep_alive_is_switched(self):
        encoder = added('src/indium/blit-command-encoder.cpp')
        holds = re.findall(r'^.*_keepAlive\.push_back\(.*$', encoder, re.M)
        self.assertGreaterEqual(len(holds), 10)
        for line in holds:
            self.assertIn("if (!Indium::AB::off('b'))", line)

    def test_depth_switch_covers_barrier_and_self_dependency(self):
        encoder = added('src/indium/render-command-encoder.cpp')
        dependency = encoder.split('VkSubpassDependency dependency {};', 1)[1].split('dependencies.push_back(dependency);', 1)[0]
        barrier = encoder.split('void Indium::PrivateRenderCommandEncoder::memoryBarrier(', 1)[1].split('\n}\n', 1)[0]
        for text in (dependency, barrier):
            self.assertIn("!Indium::AB::off('d')", text)
            for flag in ('VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT', 'VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT'):
                for line in text.splitlines():
                    if flag in line:
                        self.assertIn('depthBarriers ?', line)


@unittest.skipUnless(shutil.which('c++'), 'needs a C++ compiler')
class ABSwitchParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        header = base / 'include/indium/ab-switch.private.hpp'
        header.parent.mkdir(parents=True)
        header.write_text(added('private-include/indium/ab-switch.private.hpp'))
        (base / 'main.cpp').write_text(PROGRAM)
        cls.binary = base / 'ab'
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Werror', '-I', str(base / 'include'), str(base / 'main.cpp'), '-o', str(cls.binary)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_with(self, value):
        env = {k: v for k, v in os.environ.items() if k != 'INDIUM_AB'}
        if value is not None:
            env['INDIUM_AB'] = value
        # run in an empty directory so a stray /tmp/indium-ab on this host is the only other input
        return subprocess.run([str(self.binary)], env=env, check=True, capture_output=True, text=True, cwd=self.tmp.name).stdout.strip()

    @unittest.skipIf(Path('/tmp/indium-ab').exists(), 'a host /tmp/indium-ab would change the defaults')
    def test_unset_keeps_every_change(self):
        self.assertEqual(self.run_with(None), '00000')
        self.assertEqual(self.run_with(''), '00000')

    def test_letters_turn_single_changes_off(self):
        self.assertEqual(self.run_with('s'), '10001')
        self.assertEqual(self.run_with('td'), '01010')
        self.assertEqual(self.run_with('stbd'), '11111')


if __name__ == '__main__':
    unittest.main()
