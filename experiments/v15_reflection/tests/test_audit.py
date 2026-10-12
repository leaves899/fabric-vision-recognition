"""The reviewed-photo diagnostic must not leak operator GT into auto inference."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from experiments.v15_reflection.audit_reviewed import audit


class AuditTest(unittest.TestCase):
    def test_report_is_diagnostic_only_and_ignores_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"data").mkdir()
            (root/"ann").mkdir()
            y,x=np.indices((512,512))
            arr=np.clip(128+50*np.cos(2*np.pi*y/16)+40*np.cos(2*np.pi*x/22),0,255).astype("uint8")
            img=root/"data"/"test.png"
            Image.fromarray(arr).convert("RGB").save(img)
            sha=hashlib.sha256(img.read_bytes()).hexdigest()
            record={"sample_id":"S001","fabric_id":"SYN-S001",
                    "image_path":"data/test.png","image_sha256":sha,
                    "review_state":"OPERATOR_REVIEWED","reference_confirmed":True,
                    "segments":{"reference":[[50,110],[460,110]],
                                "check_same":[[50,220],[460,220]]}}
            (root/"ann"/"S001.json").write_text(json.dumps(record))
            record["sample_id"]="DRAFT"
            record["review_state"]="DRAFT"
            (root/"ann"/"draft.json").write_text(json.dumps(record))
            result=audit(root,root/"ann")
            self.assertEqual(result["operator_reviewed_images"],1)
            self.assertEqual(result["hash_or_photo_failures"],0)
            self.assertEqual(result["status"],"DIAGNOSTIC_ONLY_NOT_CERTIFIED")
            self.assertIsNone(result["results"][0]["measured_density_per_cm"])
            self.assertIsNotNone(result["results"][0]["manual_conditioned_pitch_A_px"])


if __name__=="__main__":
    unittest.main()
