"""
Photo, bio and research interests on the account, through the REST boundary (IR-695).

The contract these hold to is the comment on IR-695: `GET`/`PATCH /users/me/`,
`PUT`/`DELETE /users/me/photo/`, `GET /users/<id>/photo/` and
`GET /users/interests/?q=`. Messages are asserted as written because the
frontend shows them as written.
"""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APITestCase

from apps.accounts import profile
from apps.accounts.models import ResearchInterest, User
from apps.accounts.tests import make_user


class TempMedia:
    """Photos land in a throwaway MEDIA_ROOT, removed with the class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = tempfile.mkdtemp(prefix="iris-profile-media-")
        cls.addClassCleanup(shutil.rmtree, root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=root)
        override.enable()
        cls.addClassCleanup(override.disable)


def image_bytes(fmt="JPEG", size=(200, 100), left="red", right="blue", **save):
    """An image whose left half is one colour and right half another."""
    mode = "RGBA" if fmt == "PNG" and save.pop("alpha", False) else "RGB"
    image = Image.new(mode, size, left)
    image.paste(right, (size[0] // 2, 0, size[0], size[1]))
    out = io.BytesIO()
    image.save(out, fmt, **save)
    return out.getvalue()


def upload(data, name="photo.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def stored(user):
    """The image a user's photo file holds."""
    user.refresh_from_db()
    with user.photo.open("rb") as handle:
        image = Image.open(io.BytesIO(handle.read()))
        image.load()
    return image


class ProfileTestCase(TempMedia, APITestCase):
    me_url = None

    def setUp(self):
        self.me_url = reverse("user-me")
        self.photo_url = reverse("user-me-photo")
        self.ana = make_user("ana@cit.edu", "Student")
        self.ben = make_user("ben@cit.edu", "Student")
        self.client.force_authenticate(self.ana)

    def patch(self, **fields):
        return self.client.patch(self.me_url, fields, format="json")

    def put_photo(self, data=None, name="photo.jpg", content_type="image/jpeg", **fields):
        body = {"photo": upload(data if data is not None else image_bytes(), name, content_type), **fields}
        return self.client.put(self.photo_url, body, format="multipart")


class ProfilePayloadTests(ProfileTestCase):
    def test_a_new_account_reads_with_empty_values(self):
        body = self.client.get(self.me_url).data
        self.assertEqual(body["bio"], "")
        self.assertEqual(body["research_interests"], [])
        self.assertIsNone(body["photo_url"])

    def test_the_account_has_no_orcid(self):
        self.assertNotIn("orcid", self.client.get(self.me_url).data)
        response = self.patch(orcid="0000-0002-1825-0097")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("orcid", response.data)
        self.assertFalse(hasattr(self.ana, "orcid"))

    def test_the_existing_payload_is_unchanged(self):
        body = self.client.get(self.me_url).data
        for key in ("id", "email", "first_name", "last_name", "role_name", "review_access", "role_request"):
            self.assertIn(key, body)

    def test_sign_in_carries_the_same_fields(self):
        self.ana.bio = "I study reefs."
        self.ana.save()
        from apps.accounts.serializers import MeSerializer

        self.assertEqual(MeSerializer(self.ana).data["bio"], "I study reefs.")

    def test_the_administrators_user_payload_does_not_carry_them(self):
        from apps.accounts.serializers import UserSerializer

        data = UserSerializer(self.ana).data
        for key in ("bio", "research_interests", "photo_url", "photo"):
            self.assertNotIn(key, data)


class BioTests(ProfileTestCase):
    def test_a_bio_is_saved_and_returned(self):
        response = self.patch(bio="I study coastal flooding in Cebu.")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bio"], "I study coastal flooding in Cebu.")
        self.assertEqual(self.client.get(self.me_url).data["bio"], "I study coastal flooding in Cebu.")

    def test_exactly_500_characters_is_accepted(self):
        self.assertEqual(self.patch(bio="x" * 500).status_code, 200)

    def test_501_characters_is_refused_with_the_contract_message(self):
        response = self.patch(bio="x" * 501)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"bio": ["Keep your bio to 500 characters or fewer."]})
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.bio, "")

    def test_an_empty_string_clears_the_bio(self):
        self.patch(bio="Something")
        response = self.patch(bio="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bio"], "")
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.bio, "")

    def test_a_bio_keeps_its_line_breaks(self):
        self.assertEqual(self.patch(bio="One.\nTwo.").data["bio"], "One.\nTwo.")

    def test_a_null_byte_is_refused_not_a_server_error(self):
        self.assertEqual(self.patch(bio="a\x00b").status_code, 400)

    def test_a_patch_without_a_bio_leaves_it_alone(self):
        self.patch(bio="Kept")
        self.assertEqual(self.patch(first_name="Anna").data["bio"], "Kept")


class InterestTests(ProfileTestCase):
    def test_interests_are_saved_in_the_order_given(self):
        response = self.patch(research_interests=["Hydrology", "GIS", "Aquifers"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["research_interests"], ["Hydrology", "GIS", "Aquifers"])
        self.assertEqual(
            self.client.get(self.me_url).data["research_interests"], ["Hydrology", "GIS", "Aquifers"]
        )

    def test_an_interest_matching_an_existing_one_comes_back_in_its_form(self):
        self.client.force_authenticate(self.ben)
        self.patch(research_interests=["Machine Learning"])
        self.client.force_authenticate(self.ana)
        response = self.patch(research_interests=["machine learning", "GIS"])
        self.assertEqual(response.data["research_interests"], ["Machine Learning", "GIS"])
        self.assertEqual(ResearchInterest.objects.filter(name__iexact="machine learning").count(), 1)

    def test_one_person_cannot_make_two_tags_that_differ_by_case(self):
        response = self.patch(research_interests=["GIS", "gis", "Gis"])
        self.assertEqual(response.data["research_interests"], ["GIS"])
        self.assertEqual(ResearchInterest.objects.count(), 1)

    def test_duplicates_collapse_before_the_limit_is_counted(self):
        names = [f"Topic {n}" for n in range(10)]
        self.assertEqual(self.patch(research_interests=[*names, "topic 0", "TOPIC 9"]).status_code, 200)

    def test_extra_spaces_are_collapsed_and_blank_entries_dropped(self):
        response = self.patch(research_interests=["  machine   learning ", "", "   "])
        self.assertEqual(response.data["research_interests"], ["machine learning"])

    def test_ten_interests_are_accepted_and_eleven_refused(self):
        self.assertEqual(
            self.patch(research_interests=[f"Topic {n}" for n in range(10)]).status_code, 200
        )
        response = self.patch(research_interests=[f"Other {n}" for n in range(11)])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"research_interests": ["Add up to 10 research interests."]})
        self.assertEqual(self.ana.interest_links.count(), 10)  # the refused list changed nothing
        self.assertEqual(ResearchInterest.objects.filter(name__startswith="Other").count(), 0)

    def test_forty_characters_are_accepted_and_forty_one_refused(self):
        self.assertEqual(self.patch(research_interests=["x" * 40]).status_code, 200)
        response = self.patch(research_interests=["y" * 41])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data, {"research_interests": ["Keep each interest to 40 characters or fewer."]}
        )

    def test_an_empty_list_clears_the_interests(self):
        self.patch(research_interests=["GIS"])
        response = self.patch(research_interests=[])
        self.assertEqual(response.data["research_interests"], [])
        self.assertEqual(self.ana.interest_links.count(), 0)

    def test_deleting_the_last_account_that_used_a_tag_deletes_the_tag(self):
        self.patch(research_interests=["GIS", "Hydrology"])
        self.client.force_authenticate(self.ben)
        self.patch(research_interests=["GIS"])
        self.ana.delete()
        self.assertEqual(list(ResearchInterest.objects.values_list("name", flat=True)), ["GIS"])

    def test_a_tag_nobody_uses_any_more_is_deleted(self):
        self.patch(research_interests=["GIS", "Hydrology"])
        self.client.force_authenticate(self.ben)
        self.patch(research_interests=["GIS"])
        self.client.force_authenticate(self.ana)
        self.patch(research_interests=[])
        self.assertEqual(list(ResearchInterest.objects.values_list("name", flat=True)), ["GIS"])

    def test_replacing_the_list_reorders_without_duplicating_tags(self):
        self.patch(research_interests=["GIS", "Hydrology"])
        response = self.patch(research_interests=["Hydrology", "GIS"])
        self.assertEqual(response.data["research_interests"], ["Hydrology", "GIS"])
        self.assertEqual(ResearchInterest.objects.count(), 2)

    def test_a_list_that_is_not_a_list_is_refused(self):
        for value in ("GIS", {"a": 1}, 7):
            with self.subTest(value=value):
                self.assertEqual(self.patch(research_interests=value).status_code, 400)

    def test_a_null_byte_in_an_interest_is_refused(self):
        self.assertEqual(self.patch(research_interests=["a\x00b"]).status_code, 400)

    def test_a_huge_list_is_refused_without_work(self):
        response = self.patch(research_interests=[f"t{n}" for n in range(500)])
        self.assertEqual(response.data, {"research_interests": ["Add up to 10 research interests."]})


class InterestSuggestionTests(ProfileTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("user-interest-suggestions")
        self.cleo = make_user("cleo@cit.edu", "Student")
        for user, tags in {
            self.ana: ["Machine Learning", "Machine Vision", "GIS"],
            self.ben: ["Machine Learning", "Hydrology"],
            self.cleo: ["Machine Learning", "Machine Vision"],
        }.items():
            self.client.force_authenticate(user)
            self.patch(research_interests=tags)
        self.client.force_authenticate(self.ana)

    def suggest(self, q):
        response = self.client.get(self.url, {"q": q})
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_matches_contain_the_text_case_insensitively_most_used_first(self):
        self.assertEqual(self.suggest("mach"), ["Machine Learning", "Machine Vision"])
        self.assertEqual(self.suggest("MACHINE V"), ["Machine Vision"])
        self.assertEqual(self.suggest("ology"), ["Hydrology"])  # contains, not starts with

    def test_nothing_matching_or_nothing_typed_is_an_empty_list(self):
        self.assertEqual(self.suggest("zzz"), [])
        self.assertEqual(self.suggest(""), [])
        self.assertEqual(self.suggest("   "), [])
        self.assertEqual(self.client.get(self.url).data, [])

    def test_a_like_wildcard_is_text_not_a_pattern(self):
        self.assertEqual(self.suggest("%"), [])
        self.assertEqual(self.suggest("_"), [])

    def test_at_most_ten_are_returned(self):
        self.patch(research_interests=[f"Topic {n}" for n in range(10)])
        self.client.force_authenticate(self.ben)
        self.patch(research_interests=[f"Topic {n}" for n in range(10, 15)] + ["Topic 0"])
        self.assertEqual(len(self.suggest("topic")), 10)
        self.assertEqual(self.suggest("topic")[0], "Topic 0")  # used by two people

    def test_a_tag_only_a_deactivated_account_uses_is_not_offered(self):
        self.ben.is_active = False
        self.ben.save()
        self.assertEqual(self.suggest("hydro"), [])
        self.assertEqual(self.suggest("mach"), ["Machine Learning", "Machine Vision"])

    def test_a_text_longer_than_any_tag_matches_nothing(self):
        self.assertEqual(self.suggest("machine learning" + " x" * 40), [])

    def test_signing_in_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url, {"q": "mach"}).status_code, 401)


class PhotoUploadTests(ProfileTestCase):
    def test_a_jpeg_is_stored_square_and_its_url_is_returned(self):
        response = self.put_photo()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["photo_url"], f"/users/{self.ana.pk}/photo/?v=1")
        self.assertEqual(self.client.get(self.me_url).data["photo_url"], response.data["photo_url"])
        image = stored(self.ana)
        self.assertEqual((image.format, image.size), ("JPEG", (profile.PHOTO_SIDE, profile.PHOTO_SIDE)))

    def test_a_png_is_accepted(self):
        response = self.put_photo(image_bytes("PNG"), "photo.png", "image/png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(stored(self.ana).size, (512, 512))

    def test_a_16_bit_greyscale_png_keeps_its_tones(self):
        out = io.BytesIO()
        image = Image.new("I;16", (40, 40), 32768)  # mid grey
        image.save(out, "PNG")
        self.assertEqual(self.put_photo(out.getvalue(), "g.png", "image/png").status_code, 200)
        r, g, b = stored(self.ana).getpixel((256, 256))
        self.assertTrue(100 < r < 160, (r, g, b))

    def test_a_transparent_png_is_laid_on_white(self):
        data = image_bytes("PNG", size=(40, 40), left=(0, 0, 0, 0), right=(0, 0, 0, 0), alpha=True)
        self.assertEqual(self.put_photo(data, "photo.png", "image/png").status_code, 200)
        r, g, b = stored(self.ana).getpixel((10, 10))
        self.assertTrue(min(r, g, b) > 240, (r, g, b))

    def test_without_a_crop_the_centred_square_is_taken(self):
        # 200x100, red left half and blue right half: the centre square is half of each.
        self.put_photo()
        image = stored(self.ana)
        left, right = image.getpixel((20, 256)), image.getpixel((492, 256))
        self.assertGreater(left[0], 200)
        self.assertLess(left[2], 80)
        self.assertGreater(right[2], 200)
        self.assertLess(right[0], 80)

    def test_the_square_the_person_chose_is_the_one_stored(self):
        response = self.put_photo(crop_x=100, crop_y=0, crop_size=100)  # all of the blue half
        self.assertEqual(response.status_code, 200)
        image = stored(self.ana)
        for point in ((10, 10), (500, 500), (256, 256)):
            r, g, b = image.getpixel(point)
            self.assertTrue(b > 200 and r < 80, (point, (r, g, b)))

    def test_the_crop_is_measured_after_the_orientation_is_applied(self):
        # Stored 200x100 with EXIF orientation 6, so it is shown 100x200. A crop of the
        # lower square, y=100, fits what the person saw and would not fit the raw pixels.
        exif = Image.Exif()
        exif[0x0112] = 6
        response = self.put_photo(image_bytes(exif=exif), crop_x=0, crop_y=100, crop_size=100)
        self.assertEqual(response.status_code, 200, response.data)

    def test_the_stored_file_carries_no_metadata(self):
        exif = Image.Exif()
        exif[0x010F] = "SomeCamera"
        exif[0x0112] = 1
        self.put_photo(image_bytes(exif=exif))
        self.assertEqual(len(stored(self.ana).getexif()), 0)

    def test_a_crop_outside_the_image_is_refused(self):
        for crop in ((0, 0, 101), (150, 0, 100), (0, 50, 100), (0, 0, 10_000)):
            with self.subTest(crop=crop):
                response = self.put_photo(crop_x=crop[0], crop_y=crop[1], crop_size=crop[2])
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"crop_size": ["The crop must fit inside the image."]})
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.photo)

    def test_a_crop_with_a_zero_size_or_a_negative_value_says_it_does_not_fit(self):
        for field, value in (("crop_size", 0), ("crop_size", -5), ("crop_x", -1), ("crop_y", -1)):
            with self.subTest(field=field, value=value):
                body = {"crop_x": 0, "crop_y": 0, "crop_size": 50, field: value}
                response = self.put_photo(**body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {field: ["The crop must fit inside the image."]})

    def test_a_crop_that_is_not_a_whole_number_is_refused(self):
        for field, value in (("crop_y", "1.5"), ("crop_size", "wide")):
            with self.subTest(field=field, value=value):
                body = {"crop_x": 0, "crop_y": 0, "crop_size": 50, field: value}
                response = self.put_photo(**body)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_a_partial_crop_is_refused(self):
        response = self.put_photo(crop_x=10)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {"crop_y", "crop_size"})

    def test_a_file_that_is_not_an_image_is_refused_whatever_its_name(self):
        for name, content_type in (("photo.jpg", "image/jpeg"), ("photo.png", "image/png")):
            with self.subTest(name=name):
                response = self.put_photo(b"%PDF-1.7 not an image at all", name, content_type)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"photo": ["Upload a JPEG or PNG image."]})

    def test_an_image_in_another_format_is_refused_even_named_jpg(self):
        for fmt in ("GIF", "BMP", "WEBP"):
            with self.subTest(fmt=fmt):
                response = self.put_photo(image_bytes(fmt), "photo.jpg", "image/jpeg")
                self.assertEqual(response.data, {"photo": ["Upload a JPEG or PNG image."]})

    def test_a_truncated_jpeg_is_refused(self):
        response = self.put_photo(image_bytes()[:-400])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"photo": ["Upload a JPEG or PNG image."]})

    def test_a_missing_or_empty_photo_is_refused(self):
        self.assertEqual(
            self.client.put(self.photo_url, {}, format="multipart").data,
            {"photo": ["Upload a JPEG or PNG image."]},
        )
        response = self.put_photo(b"")
        self.assertEqual(response.data, {"photo": ["Upload a JPEG or PNG image."]})
        response = self.client.put(self.photo_url, {"photo": "just text"}, format="multipart")
        self.assertEqual(response.data, {"photo": ["Upload a JPEG or PNG image."]})

    def test_the_limit_is_2_mb(self):
        response = self.put_photo(b"x" * (2 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"photo": ["The photo must be 2 MB or smaller."]})

    def test_a_real_image_just_over_2_mb_is_refused_and_one_just_under_is_not(self):
        import os

        noise = Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3))
        out = io.BytesIO()
        noise.save(out, "PNG", compress_level=0)
        self.assertGreater(len(out.getvalue()), 2 * 1024 * 1024)
        self.assertEqual(self.put_photo(out.getvalue(), "n.png", "image/png").status_code, 400)

        small = io.BytesIO()
        Image.frombytes("RGB", (400, 400), os.urandom(400 * 400 * 3)).save(small, "PNG", compress_level=0)
        self.assertLess(len(small.getvalue()), 2 * 1024 * 1024)
        self.assertEqual(self.put_photo(small.getvalue(), "s.png", "image/png").status_code, 200)

    def test_an_image_with_too_many_pixels_is_refused_before_it_is_decoded(self):
        out = io.BytesIO()
        Image.new("L", (6000, 5000)).save(out, "PNG")  # 30 megapixels, a few KB on the wire
        self.assertLess(len(out.getvalue()), 2 * 1024 * 1024)
        response = self.put_photo(out.getvalue(), "big.png", "image/png")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"photo": [profile.PHOTO_TOO_MANY_PIXELS]})

    def test_a_refused_upload_keeps_the_photo_the_person_had(self):
        self.put_photo()
        before = self.client.get(self.me_url).data["photo_url"]
        self.assertEqual(self.put_photo(b"nope").status_code, 400)
        self.assertEqual(self.client.get(self.me_url).data["photo_url"], before)

    def test_a_json_body_is_not_accepted(self):
        self.assertEqual(self.client.put(self.photo_url, {"photo": "x"}, format="json").status_code, 415)

    def test_the_photo_is_not_a_field_of_the_patch(self):
        self.put_photo()
        before = self.ana.__class__.objects.get(pk=self.ana.pk).photo.name
        self.patch(photo="profile_photos/elsewhere.jpg", photo_url="/users/9/photo/?v=9", photo_version=99)
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.photo.name, self.ana.photo_version), (before, 1))

    def test_signing_in_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.put_photo().status_code, 401)
        self.assertEqual(self.client.delete(self.photo_url).status_code, 401)


class PhotoReplacementAndRemovalTests(ProfileTestCase):
    def test_a_replacement_changes_the_url_and_deletes_the_old_file(self):
        first = self.put_photo().data["photo_url"]
        self.ana.refresh_from_db()
        old_name, storage = self.ana.photo.name, self.ana.photo.storage
        self.assertTrue(storage.exists(old_name))
        with self.captureOnCommitCallbacks(execute=True):
            second = self.put_photo().data["photo_url"]
        self.assertNotEqual(first, second)
        self.assertTrue(second.endswith("?v=2"))
        self.assertFalse(storage.exists(old_name))
        self.ana.refresh_from_db()
        self.assertTrue(storage.exists(self.ana.photo.name))

    def test_a_replacement_keeps_the_old_file_until_the_change_commits(self):
        self.put_photo()
        self.ana.refresh_from_db()
        old_name, storage = self.ana.photo.name, self.ana.photo.storage
        self.put_photo()  # no on-commit callbacks run inside the test's transaction
        self.assertTrue(storage.exists(old_name))

    def test_remove_clears_the_url_and_deletes_the_file(self):
        self.put_photo()
        self.ana.refresh_from_db()
        name, storage = self.ana.photo.name, self.ana.photo.storage
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(self.photo_url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.client.get(self.me_url).data["photo_url"])
        self.assertFalse(storage.exists(name))
        self.assertEqual(self.client.get(reverse("user-photo", args=[self.ana.pk])).status_code, 404)

    def test_removing_when_there_is_none_is_not_an_error(self):
        self.assertEqual(self.client.delete(self.photo_url).status_code, 204)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.photo_version, 0)

    def test_the_version_never_goes_back_so_a_cached_photo_is_never_shown_for_a_new_one(self):
        urls = [self.put_photo().data["photo_url"]]
        self.client.delete(self.photo_url)
        urls.append(self.put_photo().data["photo_url"])
        self.assertEqual(len(set(urls)), 2)

    def test_deleting_the_account_deletes_the_stored_photo(self):
        self.put_photo()
        self.ana.refresh_from_db()
        name, storage = self.ana.photo.name, self.ana.photo.storage
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            self.ana.delete()
        self.assertFalse(storage.exists(name))
        self.assertFalse(User.objects.filter(pk=self.ana.pk).exists())

    def test_deleting_an_account_with_no_photo_is_untouched(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.ben.delete()
        self.assertFalse(User.objects.filter(pk=self.ben.pk).exists())


class PhotoServingTests(ProfileTestCase):
    def setUp(self):
        super().setUp()
        self.put_photo()
        self.ana.refresh_from_db()
        self.url = reverse("user-photo", args=[self.ana.pk])

    def test_any_signed_in_user_reads_the_image_bytes(self):
        self.client.force_authenticate(self.ben)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        image = Image.open(io.BytesIO(b"".join(response.streaming_content)))
        self.assertEqual((image.format, image.size), ("JPEG", (512, 512)))

    def test_it_is_read_through_django_behind_sign_in(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_the_stored_path_is_not_served_by_any_url(self):
        from django.conf import settings

        response = self.client.get(f"{settings.MEDIA_URL}{self.ana.photo.name}")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.ana.photo.name, str(self.client.get(self.me_url).data))

    def test_responses_forbid_sniffing_and_shared_caches(self):
        response = self.client.get(self.url)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", response["Cache-Control"])
        self.assertNotIn("public", response["Cache-Control"])

    def test_a_copy_fetched_under_the_current_version_may_be_kept_and_any_other_may_not(self):
        current = self.client.get(f"{self.url}?v={self.ana.photo_version}")
        self.assertIn("max-age=86400", current["Cache-Control"])
        stale = self.client.get(f"{self.url}?v=0")
        self.assertEqual(stale["Cache-Control"], "private, no-cache")
        self.assertEqual(self.client.get(self.url)["Cache-Control"], "private, no-cache")

    def test_a_person_with_no_photo_a_missing_person_and_a_deactivated_account_are_all_404(self):
        self.assertEqual(self.client.get(reverse("user-photo", args=[self.ben.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("user-photo", args=[999_999])).status_code, 404)
        self.ana.is_active = False
        self.ana.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_a_row_whose_file_is_gone_is_404_not_a_server_error(self):
        self.ana.photo.storage.delete(self.ana.photo.name)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class OnlyThePersonEditsTests(ProfileTestCase):
    def test_nothing_reaches_another_persons_profile(self):
        self.patch(bio="Ana's bio", research_interests=["GIS"])
        self.put_photo()
        self.client.force_authenticate(self.ben)
        # Ben's own writes land on Ben.
        self.patch(bio="Ben's bio", research_interests=["Hydrology"])
        self.put_photo()
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.bio, "Ana's bio")
        self.assertEqual([i.name for i in self.ana.research_interests.all()], ["GIS"])
        ana_photo = self.ana.photo.name
        # Ben's request names Ana in every way a request can; none changes Ana.
        self.client.patch(reverse("user-detail", args=[self.ana.pk]), {"bio": "pwned"}, format="json")
        self.client.put(reverse("user-photo", args=[self.ana.pk]), {"photo": upload(image_bytes())}, format="multipart")
        self.client.delete(reverse("user-photo", args=[self.ana.pk]))
        self.patch(id=self.ana.pk, email=self.ana.email, bio="still Ben's")
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.bio, "Ana's bio")
        self.assertEqual(self.ana.photo.name, ana_photo)

    def test_there_is_no_write_route_for_another_persons_photo(self):
        self.client.force_authenticate(self.ben)
        url = reverse("user-photo", args=[self.ana.pk])
        for method in ("put", "post", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_an_administrator_cannot_set_these_through_the_users_endpoint(self):
        rdco = make_user("rdco@cit.edu", "RDCO")
        self.client.force_authenticate(rdco)
        response = self.client.patch(
            reverse("user-detail", args=[self.ana.pk]),
            {"bio": "By RDCO", "research_interests": ["Forced"], "first_name": "Anna"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.first_name, self.ana.bio), ("Anna", ""))
        self.assertFalse(ResearchInterest.objects.exists())
