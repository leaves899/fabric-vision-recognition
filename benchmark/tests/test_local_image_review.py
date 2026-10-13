"""Local-phone-photo reviewer: real disk, hash, API and GT isolation tests."""
from __future__ import annotations

import csv
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

from PIL import Image

from benchmark.dataset import MANIFEST_FIELDS
from benchmark.local_image_review import (validate_local_review, store_local_review,
                                          load_local_review, audit_local_reviews,
                                          review_path, FOLDER, SOURCE)
from benchmark.manual_annotation import AnnotationHandler


class LocalEvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        folder=self.root/"datasets/public_samples/images/twill"
        folder.mkdir(parents=True)
        self.imgpath="datasets/public_samples/images/twill/photo.jpg"
        Image.new("RGB",(240,180),(28,85,142)).save(self.root/self.imgpath)
        with (self.root/"datasets/manifest.csv").open("w",encoding="utf-8",newline="") as fh:
            writer=csv.DictWriter(fh,fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerow(dict(zip(MANIFEST_FIELDS,[
                "PUBLIC-T001","T001","UNKNOWN","DEV","PUBLIC_UNKNOWN",
                self.imgpath,"","NONE","NO","synthetic local reviewer test"])))
        self.a={"schema_version":"1.0","sample_id":"T001","image_path":self.imgpath,
                "annotation_source":SOURCE,"independent_physical_gt":False,
                "review_state":"OPERATOR_REVIEWED","notes":"phone visual judgment only",
                "regions":[
                    {"id":"r0001","kind":"APPARENT_VISIBLE_YARN",
                     "geometry":{"type":"LINE","points":[[10,30],[170,34]]},"note":"not independent GT"},
                    {"id":"r0002","kind":"TWILL_PATTERN",
                     "geometry":{"type":"RECT","bbox":[30,60,150,110]},"note":""},
                    {"id":"r0003","kind":"UNCERTAIN",
                     "geometry":{"type":"RECT","bbox":[70,120,100,145]},"note":""}],
                "relations":[{"a":"r0001","b":"r0002","relation":"DIFFERENT_PHYSICAL_YARN"},
                             {"a":"r0001","b":"r0003","relation":"UNKNOWN"}]}

    def test_roundtrip_file_survives_and_does_not_modify_yarn_reference(self):
        old=self.root/"datasets/annotations/drafts/T001.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"protect":"original reference"}\n',encoding="utf-8")
        protected=old.read_bytes()
        saved=store_local_review(self.root,self.a)
        target=review_path(self.root,"T001")
        self.assertTrue(target.exists())
        self.assertIn(str(FOLDER),str(target))
        self.assertEqual(protected,old.read_bytes())
        self.assertEqual(saved["annotation_target"],"LOCAL_IMAGE_EVIDENCE_REVIEW")
        self.assertFalse(saved["independent_physical_gt"])
        self.assertEqual(saved["coordinate_space"],"IMAGE_NATIVE_PIXELS")
        loaded=load_local_review(self.root,"T001")
        self.assertEqual(loaded["regions"],saved["regions"])
        self.assertEqual(loaded["relations"],saved["relations"])
        report=audit_local_reviews(self.root)
        self.assertEqual(report["saved_samples"],1)
        self.assertEqual(report["region_counts"]["TWILL_PATTERN"],1)
        self.assertEqual(report["relations"],2)

    def test_rejects_fake_physical_verification_and_bad_source(self):
        self.a["independent_physical_gt"]=True
        with self.assertRaisesRegex(ValueError,"ground truth"):
            validate_local_review(self.root,self.a)
        self.a["independent_physical_gt"]=False
        self.a["annotation_source"]="MICROSCOPE_PHYSICAL_CONFIRMATION"
        with self.assertRaisesRegex(ValueError,"ground truth"):
            validate_local_review(self.root,self.a)

    def test_rejects_bad_coords_duplicate_relation_and_stale_hash(self):
        self.a["regions"][1]["geometry"]["bbox"]=[-1,60,150,110]
        with self.assertRaisesRegex(ValueError,"outside"):
            validate_local_review(self.root,self.a)
        self.a["regions"][1]["geometry"]["bbox"]=[30,60,150,110]
        self.a["relations"].append({"a":"r0002","b":"r0001","relation":"UNKNOWN"})
        with self.assertRaisesRegex(ValueError,"duplicate pair"):
            validate_local_review(self.root,self.a)
        self.a["relations"].pop()
        self.a["image_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            validate_local_review(self.root,self.a)

    def test_true_yarn_and_false_twill_tracks_have_same_line_geometry(self):
        # New twill short-line supports comparable positive/negative candidates.
        # It remains a PHONE_IMAGE_OPERATOR_REVIEW hypothesis, not physical GT.
        self.a["regions"][1]["geometry"]={
            "type":"LINE","points":[[30,60],[150,110]]}
        saved=store_local_review(self.root,self.a)
        self.assertEqual(saved["regions"][1]["kind"],"TWILL_PATTERN")
        self.assertEqual(saved["regions"][1]["geometry"]["type"],"LINE")
        self.assertFalse(saved["regions"][1]["physical_identity_confirmed"])
        self.assertEqual(load_local_review(self.root,"T001")["regions"][1]["geometry"]["type"],"LINE")
        self.assertFalse(saved["independent_physical_gt"])

    def test_legacy_twill_rectangles_still_roundtrip(self):
        saved=store_local_review(self.root,self.a)
        self.assertEqual(saved["regions"][1]["kind"],"TWILL_PATTERN")
        self.assertEqual(saved["regions"][1]["geometry"]["type"],"RECT")
        self.assertEqual(load_local_review(self.root,"T001")["regions"][1]["geometry"]["type"],"RECT")

    def test_only_approved_local_image_categories_can_have_short_line(self):
        self.a["regions"][0]["kind"]="SHADOW"
        with self.assertRaisesRegex(ValueError,"short line"):
            validate_local_review(self.root,self.a)
        self.a["regions"][0]["kind"]="APPARENT_VISIBLE_YARN"
        self.a["relations"][0]["b"]="r5000"
        with self.assertRaisesRegex(ValueError,"two different saved"):
            validate_local_review(self.root,self.a)

    def test_missing_file_returns_empty_git_trackable_draft(self):
        data=load_local_review(self.root,"T001")
        self.assertEqual(data["regions"],[])
        self.assertEqual(data["relations"],[])
        self.assertFalse(data["independent_physical_gt"])
        self.assertEqual(data["review_state"],"DRAFT")

    def test_http_get_post_roundtrip_on_localhost_and_reject_foreign_origin(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),
            lambda *args,**kw: AnnotationHandler(*args,directory=str(self.root),**kw))
        server.repo_root=self.root
        t=threading.Thread(target=server.serve_forever,daemon=True)
        t.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),t.join(timeout=3)))
        url=f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(url+"/api/local-review?id=T001") as response:
            self.assertEqual(json.load(response)["regions"],[])
        data=json.dumps(self.a).encode("utf-8")
        req=urllib.request.Request(url+"/api/local-review",data=data,
             headers={"Content-Type":"application/json","Origin":url},method="POST")
        with urllib.request.urlopen(req) as response:
            result=json.load(response)
        self.assertTrue(result["saved"])
        self.assertEqual(result["regions"],3)
        self.assertEqual(result["relations"],2)
        self.assertTrue(review_path(self.root,"T001").exists())
        foreign=urllib.request.Request(url+"/api/local-review",data=data,
             headers={"Origin":"https://example.org","Content-Type":"application/json"},method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(foreign)
        self.assertEqual(cm.exception.code,403)
        self.assertEqual(audit_local_reviews(self.root)["saved_samples"],1)


if __name__=="__main__":
    unittest.main()
