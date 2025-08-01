import contextlib
import copy
import traceback

import jsonpatch
from jsonpatch import JsonPatchException
from jsonpointer import JsonPointerException

from . import ElectrumTestCase


class TestJsonpatch(ElectrumTestCase):

    async def test_op_replace(self):
        data1 = {'foo': 'bar', 'numbers': [1, 3, 4, 8], 'dictlevelA1': {'secret1': 2, 'secret2': 4, 'secret3': 6}}
        patches = [{"op": "replace", "path": "/dictlevelA1/secret2", "value": 2222}]
        jpatch = jsonpatch.JsonPatch(patches)
        data2 = jpatch.apply(data1)
        self.assertEqual(
            {'foo': 'bar', 'numbers': [1, 3, 4, 8], 'dictlevelA1': {'secret1': 2, 'secret2': 2222, 'secret3': 6}},
            data2
        )

    @contextlib.contextmanager
    def _customAssertRaises(self, *args, **kwargs):
        with self.assertRaises(*args, **kwargs) as ctx:
            try:
                yield ctx
            except Exception as e:
                # save original traceback now, as assertRaises will destroy most of it imminently:
                ctx._customctx_original_tb = "".join(traceback.format_exception(e))
                raise

    async def test_patch_does_not_leak_privatekeys(self):
        data1 = {
            'dictlevelB1': 'secret77',
            'dictlevelC1': [1, "secret99", 4, 8],
            'dictlevelA1': {"dictlevelA2_aa": "secret11", "dictlevelA2_bb": "secret12", "dictlevelA2_cc": "secret13"}}
        def fail_if_leaking_secret(ctx) -> None:
            self.assertNotIn("secret", str(ctx.exception))
            self.assertNotIn("secret", repr(ctx.exception))
            self.assertNotIn("secret", ctx._customctx_original_tb)
            self.assertNotIn("dictlevel", str(ctx.exception))
            self.assertNotIn("dictlevel", repr(ctx.exception))
            self.assertNotIn("dictlevel", ctx._customctx_original_tb)
            self.assertIn("redacted", str(ctx.exception))  # injected by our monkeypatching
            self.assertIn("redacted", repr(ctx.exception))  # injected by our monkeypatching
        # op "replace"
        with self.subTest(msg="replace_dict_inner_key_missing"):
            patches = [{"op": "replace", "path": "/dictlevelA1/dictlevelX2", "value": "nakamoto_secret"}]
            jpatch = jsonpatch.JsonPatch(patches)
            with self._customAssertRaises(JsonPatchException) as ctx:
                data2 = jpatch.apply(data1)
            fail_if_leaking_secret(ctx)
        with self.subTest(msg="replace_dict_outer_key_missing"):
            patches = [{"op": "replace", "path": "/dictlevelX1/dictlevelX2", "value": "nakamoto_secret"}]
            jpatch = jsonpatch.JsonPatch(patches)
            with self._customAssertRaises(JsonPointerException) as ctx:
                data2 = jpatch.apply(data1)
            fail_if_leaking_secret(ctx)
        # op "remove"
        with self.subTest(msg="remove_dict_inner_key_missing"):
            patches = [{"op": "remove", "path": "/dictlevelA1/dictlevelX2"}]
            jpatch = jsonpatch.JsonPatch(patches)
            with self._customAssertRaises(JsonPatchException) as ctx:
                data2 = jpatch.apply(data1)
            fail_if_leaking_secret(ctx)
        with self.subTest(msg="remove_dict_outer_key_missing"):
            patches = [{"op": "remove", "path": "/dictlevelX1/dictlevelX2"}]
            jpatch = jsonpatch.JsonPatch(patches)
            with self._customAssertRaises(JsonPointerException) as ctx:
                data2 = jpatch.apply(data1)
            fail_if_leaking_secret(ctx)
        # op "add"
        with self.subTest(msg="add_dict_inner_key_missing"):
            patches = [{"op": "add", "path": "/dictlevelA1/dictlevelX2/dictlevelX3/dictlevelX4", "value": "nakamoto_secret"}]
            jpatch = jsonpatch.JsonPatch(patches)
            with self._customAssertRaises(JsonPointerException) as ctx:
                data2 = jpatch.apply(data1)
            fail_if_leaking_secret(ctx)
        with self.subTest(msg="add_dict_outer_key_missing"):
            patches = [{"op": "add", "path": "/dictlevelX1/dictlevelX2/dictlevelX3/dictlevelX4", "value": "nakamoto_secret"}]
            jpatch = jsonpatch.JsonPatch(patches)
            with self._customAssertRaises(JsonPointerException) as ctx:
                data2 = jpatch.apply(data1)
            fail_if_leaking_secret(ctx)
