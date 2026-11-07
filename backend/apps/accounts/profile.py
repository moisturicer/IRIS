"""
The optional parts of a person's account: photo, bio and research interests
(IR-695, spec IR-694).

Each is the person's alone to edit -- the only routes that write them act on
`request.user` -- and each can be cleared. This module holds the rules; the
serializer and views only carry them to HTTP.

**The photo is re-encoded, never stored as uploaded.** The upload is opened by
what it contains (Pillow, restricted to JPEG and PNG), its orientation is
applied, the square the person chose is cut out, and a fresh 512x512 JPEG is
written. A file that merely ends in `.png`, a polyglot, EXIF metadata (which can
carry a GPS position) and an animated image all stop at that step.
"""

from __future__ import annotations

import io

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Value
from django.db.models.functions import Lower
from PIL import Image, ImageOps
from rest_framework.exceptions import ValidationError

from .models import ResearchInterest, User, UserInterest, delete_photo_file

BIO_MAX_LENGTH = 500
INTERESTS_MAX = 10
INTEREST_MAX_LENGTH = 40
SUGGESTIONS_MAX = 10
#: A list longer than this is refused unread: nobody meant it, and it is not worth scanning.
INTERESTS_SCAN_CEILING = 10 * INTERESTS_MAX

PHOTO_MAX_BYTES = 2 * 1024 * 1024
#: The stored photo's side, in pixels.
PHOTO_SIDE = 512
#: Pixels, not bytes: a 2 MB PNG can decode to hundreds of megabytes. Refused
#: from the header, before anything is decoded.
PHOTO_MAX_PIXELS = 25_000_000
PHOTO_QUALITY = 88

# Shown as written by the frontend (the IR-695 contract's error list).
BIO_TOO_LONG = f"Keep your bio to {BIO_MAX_LENGTH} characters or fewer."
TOO_MANY_INTERESTS = f"Add up to {INTERESTS_MAX} research interests."
INTEREST_TOO_LONG = f"Keep each interest to {INTEREST_MAX_LENGTH} characters or fewer."
NOT_AN_IMAGE = "Upload a JPEG or PNG image."
PHOTO_TOO_LARGE = "The photo must be 2 MB or smaller."
CROP_OUTSIDE = "The crop must fit inside the image."
# Not in the contract's list; added for cases it did not foresee.
PHOTO_TOO_MANY_PIXELS = "The photo is too large in pixels. Upload one up to 25 megapixels."
CROP_INCOMPLETE = "Send crop_x, crop_y and crop_size together, or none of them."


# -- Interests ---------------------------------------------------------------

def clean_interests(items) -> list[str]:
    """
    Tidy a list of tags the way a person meant it, or refuse it.

    Whitespace is collapsed and trimmed, empty entries are dropped, and a tag
    repeated in another case collapses into its first spelling. The limits apply
    to what is left, so a list with duplicates in it is not refused for them.
    """
    if len(items) > INTERESTS_SCAN_CEILING:
        raise ValidationError(TOO_MANY_INTERESTS)
    names, seen = [], set()
    for item in items:
        name = " ".join(item.split())
        if not name:
            continue
        if len(name) > INTEREST_MAX_LENGTH:
            raise ValidationError(INTEREST_TOO_LONG)
        key = name.lower()  # PostgreSQL's lower(), as the unique index uses, not casefold()
        if key not in seen:
            seen.add(key)
            names.append(name)
    if len(names) > INTERESTS_MAX:
        raise ValidationError(TOO_MANY_INTERESTS)
    return names


def interest_names(user: User) -> list[str]:
    """The person's interests, in the order they gave them."""
    return list(user.interest_links.values_list("interest__name", flat=True))


def _interest_named(name: str) -> ResearchInterest:
    """The existing tag `name` matches in any case, or a new one.

    Both sides are lowered by PostgreSQL, the function the unique index uses,
    so a lookup and the constraint cannot disagree about what "the same" is.
    """
    matching = ResearchInterest.objects.annotate(lowered=Lower("name")).filter(
        lowered=Lower(Value(name))
    )
    existing = matching.first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():  # a savepoint: losing the race must not poison the caller's transaction
            return ResearchInterest.objects.create(name=name)
    except IntegrityError:  # someone added the same tag between the lookup and the insert
        return matching.get()


def set_interests(user: User, names: list[str]) -> None:
    """Replace the person's interests with `names` (already `clean_interests`)."""
    with transaction.atomic():
        before = set(user.interest_links.values_list("interest_id", flat=True))
        tags = []
        for name in names:
            tag = _interest_named(name)
            if tag not in tags:
                tags.append(tag)
        user.interest_links.all().delete()
        UserInterest.objects.bulk_create(
            UserInterest(user=user, interest=tag, position=position)
            for position, tag in enumerate(tags)
        )
        # A tag nobody uses any more goes, so suggestions offer only what a
        # current account carries.
        released = before - {tag.pk for tag in tags}
        ResearchInterest.objects.filter(pk__in=released, user_links__isnull=True).delete()


def suggest_interests(query: str) -> list[str]:
    """Up to ten tags in use by an active account whose name contains `query`, most used first."""
    query = query.strip()
    if not query or len(query) > INTEREST_MAX_LENGTH:  # nothing that long can match a tag
        return []
    return list(
        ResearchInterest.objects.filter(name__icontains=query)
        .annotate(uses=Count("user_links", filter=Q(user_links__user__is_active=True)))
        .filter(uses__gt=0)
        .order_by("-uses", "name")
        .values_list("name", flat=True)[:SUGGESTIONS_MAX]
    )


# -- Photo -------------------------------------------------------------------

def prepare_photo(upload, crop: tuple[int, int, int] | None) -> bytes:
    """
    The bytes to store for `upload`: a 512x512 JPEG of the chosen square.

    `crop` is `(x, y, side)` in pixels of the image as a person sees it (its
    orientation applied), or None for the largest centred square. Anything that
    is not a readable JPEG or PNG raises the contract's `photo` error.
    """
    if upload.size > PHOTO_MAX_BYTES:
        raise ValidationError({"photo": [PHOTO_TOO_LARGE]})
    try:
        upload.seek(0)
        image = Image.open(upload, formats=("JPEG", "PNG"))
        if image.width * image.height > PHOTO_MAX_PIXELS:
            raise ValidationError({"photo": [PHOTO_TOO_MANY_PIXELS]})
        image.load()  # decodes everything, so a truncated file fails here and not at save time
        image = ImageOps.exif_transpose(image)
    except ValidationError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        # OSError covers Pillow's UnidentifiedImageError and a truncated file;
        # SyntaxError is what a corrupt PNG chunk raises.
        raise ValidationError({"photo": [NOT_AN_IMAGE]})

    width, height = image.size
    if crop is None:
        side = min(width, height)
        left, top = (width - side) // 2, (height - side) // 2
    else:
        left, top, side = crop
        if side < 1 or left + side > width or top + side > height:
            raise ValidationError({"crop_size": [CROP_OUTSIDE]})
    square = image.crop((left, top, left + side, top + side))
    if square.mode.startswith("I;16"):  # 16-bit greyscale: scale to 8 bits, or convert() clips it to white
        square = square.point(lambda value: value / 256).convert("L")

    # JPEG has no transparency: lay it on white rather than let it turn black.
    if square.mode in ("RGBA", "LA", "PA") or "transparency" in square.info:
        rgba = square.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
    else:
        flat = square.convert("RGB")
    flat = flat.resize((PHOTO_SIDE, PHOTO_SIDE), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    flat.save(out, "JPEG", quality=PHOTO_QUALITY, optimize=True)  # no EXIF or ICC is carried over
    return out.getvalue()


def set_photo(user: User, upload, crop: tuple[int, int, int] | None) -> None:
    """Store `upload` as the person's photo, replacing any earlier one."""
    data = prepare_photo(upload, crop)  # before the row lock: decoding is the slow part
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        old = locked.photo.name or None
        locked.photo.save("photo.jpg", ContentFile(data), save=False)
        locked.photo_version += 1
        try:
            locked.save(update_fields=["photo", "photo_version"])
        except Exception:
            delete_photo_file(locked.photo.name)  # the row did not take it: do not orphan the file
            raise
        if old:  # after commit, so a failed request cannot leave a row naming a deleted file
            transaction.on_commit(lambda: delete_photo_file(old), robust=True)
    user.photo, user.photo_version = locked.photo, locked.photo_version


def remove_photo(user: User) -> None:
    """Remove the person's photo and delete its file. Removing none is not an error."""
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if not locked.photo:
            return
        old = locked.photo.name
        locked.photo = None
        locked.photo_version += 1
        locked.save(update_fields=["photo", "photo_version"])
        transaction.on_commit(lambda: delete_photo_file(old), robust=True)
    user.photo, user.photo_version = locked.photo, locked.photo_version


def photo_url(user: User) -> str | None:
    """Where the photo is read, relative to the API base; None without one."""
    if not user.photo:
        return None
    return f"/users/{user.pk}/photo/?v={user.photo_version}"
