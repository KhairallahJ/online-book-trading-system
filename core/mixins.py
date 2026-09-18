from django.contrib.auth.mixins import UserPassesTestMixin


class StaffRequiredMixin(UserPassesTestMixin):
    """Limit a class-based view to staff: anonymous users go to login, everyone else gets a 403."""

    def test_func(self):
        return self.request.user.is_staff


class OwnerOrStaffRequiredMixin(UserPassesTestMixin):
    """Limit a single-object view to users the object allows (its ``can_edit(user)``), e.g. owner or staff.

    Anonymous users go to login; other users get a 403.
    """

    def get_object(self, queryset=None):
        # test_func and the view both need the object; fetch it once.
        if not hasattr(self, '_object'):
            self._object = super().get_object(queryset)
        return self._object

    def test_func(self):
        return self.get_object().can_edit(self.request.user)
