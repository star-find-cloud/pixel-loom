from io import BytesIO
import json
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from pixel_workbench.updates import (API_URL, MAX_RESPONSE_BYTES, RELEASES_URL, UpdateError,
                                    Version, expected_download_url, fetch_latest, select_release,
                                    valid_download_url)


def release_data(tag="v0.7.8", preview=False, asset=True, **fields):
    item = {"tag_name": tag, "draft": False, "prerelease": preview,
            "name": "Pixel Loom " + tag, "body": "Updated editor", "assets": []}
    if asset:
        item["assets"].append({"state": "uploaded", "size": 100_000,
                               "browser_download_url": expected_download_url(tag)})
    item.update(fields)
    return item


class UpdateTests(unittest.TestCase):
    def test_numeric_versions_are_compared_numerically(self):
        self.assertGreater(Version.parse("v0.10.0"), Version.parse("0.9.99"))
        self.assertGreater(Version.parse("1.0.0"), Version.parse("0.99.99"))
        self.assertEqual(Version.parse("v0.7.8+windows.1"), Version.parse("0.7.8+windows.2"))

    def test_prerelease_order_follows_semantic_versioning(self):
        ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                   "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        versions = [Version.parse(item) for item in ordered]
        self.assertEqual(sorted(reversed(versions)), versions)

    def test_invalid_tags_are_ignored_without_becoming_links(self):
        for tag in (None, "", "main", "v0.7", "v00.7.8", "0.7.8-01", "../../evil", "https://other.invalid"):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    Version.parse(tag)
        self.assertIsNone(select_release([{"tag_name": "main"}, None, {"tag_name": "v0.7.8", "draft": True}]))

    def test_selects_highest_version_independent_of_api_order(self):
        result = select_release([release_data("v0.7.9"), release_data("v0.7.8"), release_data("v0.10.0")])
        self.assertEqual(result.number, "0.10.0")
        self.assertEqual(result.page_url, RELEASES_URL + "/tag/v0.10.0")

    def test_preview_channel_supports_existing_public_test_releases(self):
        data = [release_data("v0.7.6", preview=True), release_data("v0.7.8-beta.1", preview=False),
                release_data("v0.7.5"), release_data("v9.0.0", draft=True)]
        self.assertEqual(select_release(data).number, "0.7.8-beta.1")
        self.assertEqual(select_release(data, include_prereleases=False).number, "0.7.5")
        self.assertIsNone(select_release([data[0]], include_prereleases=False))

    def test_release_text_is_bounded_and_links_come_from_known_repository(self):
        result = select_release([release_data(body="x"*30_000, name="y"*300,
                                              html_url="https://other.invalid/malware")])
        self.assertEqual(len(result.notes), 20_000)
        self.assertEqual(len(result.name), 200)
        self.assertTrue(result.page_url.startswith(RELEASES_URL + "/tag/"))

    def test_download_accepts_only_this_repositorys_exact_windows_archive(self):
        trusted = expected_download_url("v0.7.8")
        self.assertTrue(valid_download_url(trusted, "v0.7.8"))
        for url in (trusted.replace("https:", "http:"), trusted.replace("github.com", "github.com.evil.invalid"),
                    trusted.replace("pixel-loom/", "different-repo/"), trusted + "?next=evil",
                    trusted.replace(".zip", ".exe"), trusted.replace("v0.7.8/", "v9.0.0/"), None):
            with self.subTest(url=url):
                self.assertFalse(valid_download_url(url, "v0.7.8"))
        item = release_data()
        item["assets"][0]["browser_download_url"] = "https://other.invalid/download.zip"
        self.assertIsNone(select_release([item]).download_url)

    def test_missing_or_unfinished_windows_package_keeps_release_page(self):
        for fields in ({"assets": []}, {"assets": None}, {"assets": [{"state": "new", "browser_download_url": expected_download_url("v0.7.8")}]},
                       {"assets": [{"state": "uploaded", "browser_download_url": RELEASES_URL + "/download/v0.7.8/source.zip"}]}):
            result = select_release([release_data(**fields)])
            self.assertIsNone(result.download_url)
            self.assertEqual(result.page_url, RELEASES_URL + "/tag/v0.7.8")

    def test_fetch_uses_a_bounded_public_get_with_no_artwork_or_credentials(self):
        opener = Mock(return_value=BytesIO(json.dumps([release_data()]).encode()))
        result = fetch_latest(opener=opener)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(opener.call_args.kwargs["timeout"], 8)
        self.assertEqual(result.download_url, expected_download_url("v0.7.8"))

    def test_network_errors_become_actionable_messages_without_raw_secrets(self):
        for error in (URLError("private proxy credential"), TimeoutError("private socket"),
                      HTTPError(API_URL, 403, "private error", {}, None),
                      HTTPError(API_URL, 404, "private error", {}, None)):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(UpdateError) as caught:
                    fetch_latest(opener=Mock(side_effect=error))
                self.assertIn("页面", str(caught.exception))
                self.assertNotIn("private", str(caught.exception))

    def test_invalid_or_oversized_response_is_rejected(self):
        for payload in (b"not json", b'{"message":"unexpected object"}', b"x"*(MAX_RESPONSE_BYTES+1)):
            with self.subTest(length=len(payload)):
                with self.assertRaises(UpdateError):
                    fetch_latest(opener=Mock(return_value=BytesIO(payload)))

    def test_null_optional_fields_and_empty_releases_are_supported(self):
        self.assertIsNone(select_release([]))
        result = select_release([release_data(name=None, body=None)])
        self.assertEqual(result.name, "v0.7.8")
        self.assertEqual(result.notes, "")
