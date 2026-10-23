# 不需要联网、不需要 Chrome：python3 -m unittest discover -s tests
import json, os, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, 'cocut'))
import draft, api

class Draft(unittest.TestCase):
    def test_hello_script(self):
        src = draft.parse(open(os.path.join(ROOT, 'examples/hello/script.md'), encoding='utf-8').read())
        self.assertEqual(src['title'], '先改，再渲染'); self.assertEqual(len(src['beats']), 9)
        b = {x['id']: x for x in src['beats']}
        self.assertTrue(b['2b'].get('hero')); self.assertTrue(b['3b'].get('title')); self.assertEqual(b['0b']['move'], 'pan')
    def test_build_without_voice(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, os.path.join(ROOT, 'cocut/cli.py'), 'new', os.path.join(ROOT, 'examples/hello/script.md'), d, '--no-voice'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.load(open(os.path.join(d, 'doc.json'), encoding='utf-8'))
            self.assertIsNone(doc['music']); self.assertTrue(all(x['dur'] >= 2.2 for x in doc['beats']))
            plan = api.to_plan(doc); self.assertEqual(len(plan['beats']), 9)

class Layer(unittest.TestCase):
    def doc(self):
        return dict(style=dict(sub_size=40, note_size=30), beats=[
            dict(id='a', dur=4, image='a.jpg', caption='小字', vo=dict(text='这是一句旁白。', lead=0.2, dur=3)),
            dict(id='b', dur=3, image='b.jpg')])
    def test_hits(self):
        d = self.doc()
        self.assertEqual(api.layer_at(d, 2, 0.5, 0.926)['kind'], 'sub')
        self.assertEqual(api.layer_at(d, 2, 0.5, 0.10)['kind'], 'caption')
        self.assertEqual(api.layer_at(d, 2, 0.5, 0.5), dict(kind='image', beat='a', src='a.jpg'))
        self.assertEqual(api.layer_at(d, 3.95, 0.5, 0.5)['beat'], 'b')      # 交叉淡化后半段算下一拍

if __name__ == '__main__': unittest.main()
