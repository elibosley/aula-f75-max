"""Progress stays observable during a transfer and never creates a second write."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import unittest
from hardware_progress import ProgressStore
from keyboard_customize import Keyboard,BUNDLE_BYTES

class ProgressTest(unittest.TestCase):
    def test_duplicate_operation_is_rejected_and_completion_is_explicit(self):
        store=ProgressStore();key='a'*32;store.begin(key,'save')
        store.update(key,'sending',3232,3232)
        self.assertEqual(store.get(key)['state'],'running')
        store.update(key,'saving')
        self.assertIsNone(store.get(key)['completed'])
        with self.assertRaises(ValueError):store.begin(key,'save')
        store.update(key,'verifying',3232,3232)
        self.assertEqual(store.get(key)['state'],'running')
        store.finish(key,False)
        self.assertEqual(store.get(key)['state'],'error')
        store.update(key,'sending',1,10)
        self.assertEqual(store.get(key)['phase'],'verifying')

    def test_retention_is_bounded_without_evicting_a_live_operation(self):
        store=ProgressStore(limit=2);first='a'*32;second='b'*32;third='c'*32
        store.begin(first,'read');store.begin(second,'save')
        with self.assertRaises(RuntimeError):store.begin(third,'save')
        store.finish(second,True);store.begin(third,'read')
        self.assertEqual(store.get(first)['state'],'running')
        self.assertIsNone(store.get(second))
        self.assertEqual(set(store.get(first)),{'action','state','phase','completed','total'})

    def test_usb_reports_only_acknowledged_bytes_and_stops_on_failure(self):
        keyboard=Keyboard();events=[];keyboard.progress=lambda *args:events.append(args)
        calls=[]
        def exchange(op,offset=0,payload=b''):
            calls.append(op)
            if op==5 and offset>=34:raise RuntimeError('Lost device')
            return bytes(32)
        keyboard.exchange=exchange
        with self.assertRaisesRegex(RuntimeError,'Lost device'):keyboard.read()
        self.assertEqual([e for e in events if len(e)==3],[('reading',17,BUNDLE_BYTES),('reading',34,BUNDLE_BYTES)])
        self.assertEqual(calls[-1],6)

if __name__=='__main__':unittest.main()
