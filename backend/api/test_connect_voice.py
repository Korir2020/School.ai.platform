from django.core.files.uploadedfile import SimpleUploadedFile

from api.test_connect_attachments import AttachmentTests as Base

SAMPLES = {
    "audio/webm": b"\x1a\x45\xdf\xa3" + b"\x00" * 64,
    "audio/ogg": b"OggS" + b"\x00" * 64,
    "audio/mp4": b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64,
    "audio/mpeg": b"ID3\x04" + b"\x00" * 64,
}


class VoiceNoteTests(Base):
    def test_each_audio_type_accepted_and_played_inline(self):
        for kind, data in SAMPLES.items():
            r = self.post([SimpleUploadedFile("voice.bin", data)])
            self.assertEqual(r.status_code, 201, (kind, r.data))
            att = r.data["attachments"][0]
            self.assertEqual(att["type"], kind)
            d = self.client_for(self.parent).get(f"/api/connect/attachments/{att['id']}/")
            self.assertTrue(d["Content-Disposition"].startswith("inline"))

    def test_fake_audio_by_name_rejected(self):
        r = self.post([SimpleUploadedFile("voice.webm", b"not audio at all" * 4)])
        self.assertEqual(r.status_code, 400)

    def test_voice_note_over_5mb_rejected(self):
        big = SAMPLES["audio/webm"] + b"\x00" * (5 * 1024 * 1024)
        r = self.post([SimpleUploadedFile("voice.webm", big)])
        self.assertEqual(r.status_code, 400)
