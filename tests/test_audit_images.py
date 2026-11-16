from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from PIL import Image, PngImagePlugin

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_images import audit

class ImageAuditTests(unittest.TestCase):
    def test_bytes_pixels_and_filename_are_distinct_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dev=root/'dev';ref=root/'ref';dev.mkdir();ref.mkdir()
            a=Image.new('RGB',(16,16),'red');a.save(ref/'video_site_0010.png')
            shutil.copyfile(ref/'video_site_0010.png',dev/'renamed.png')
            meta=PngImagePlugin.PngInfo();meta.add_text('note','Different metadata')
            a.save(dev/'video_site_0012.png',pnginfo=meta)
            Image.new('RGB',(16,16),'blue').save(dev/'video_site_0010.png')
            report=audit(dev,ref);s=report['summary']
            self.assertEqual(s['cross_set_same_filename'],1)
            self.assertEqual(s['cross_set_byte_identical'],1)
            self.assertEqual(s['cross_set_pixel_identical'],2)
            self.assertEqual(s['development_internal_byte_duplicate_groups'],0)
            self.assertEqual(s['development_internal_pixel_duplicate_groups'],1)
            self.assertEqual(s['shared_video_ids'],1)
            self.assertEqual(s['decode_errors'],0)

    def test_bad_image_is_reported_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dev=root/'dev';ref=root/'ref';dev.mkdir();ref.mkdir()
            (dev/'broken.jpg').write_bytes(b'not an image')
            report=audit(dev,ref)
            self.assertEqual(report['summary']['development_images'],1)
            self.assertEqual(report['summary']['decode_errors'],1)
            self.assertEqual(report['summary']['cross_set_pixel_identical'],0)

if __name__=='__main__':unittest.main()
