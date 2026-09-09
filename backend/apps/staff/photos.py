from django.core.exceptions import ObjectDoesNotExist


def profile_photo(profile):
    if profile.profile_photo_removed:
        return None
    if profile.profile_photo:
        return profile.profile_photo
    try:
        photo = profile.practitioner_profile.source_application.profile_photo
        if photo:
            return photo
    except (ObjectDoesNotExist, AttributeError):
        pass
    return profile.profile_photo
