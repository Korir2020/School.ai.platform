from django.test import SimpleTestCase

from learning.catalog_api import _youtube_embed

OK = "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"


class YoutubeEmbedTests(SimpleTestCase):
    def test_valid_forms(self):
        for u in (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
        ):
            self.assertEqual(_youtube_embed("video", u), OK, u)

    def test_rejected(self):
        for u in (
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
            "https://evil.example/youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com@evil.example/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com:8443/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXc",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXc!",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&v=aaaaaaaaaaa",
            "https://www.youtube.com/playlist?list=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ/extra",
            "javascript:alert(1)",
            "",
        ):
            self.assertIsNone(_youtube_embed("video", u), u)

    def test_only_video_type(self):
        u = "https://youtu.be/dQw4w9WgXcQ"
        for t in ("lesson", "external_link", "article", "other"):
            self.assertIsNone(_youtube_embed(t, u), t)
        self.assertIsNone(_youtube_embed("video", None))
