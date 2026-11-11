from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from .models import User, UserRole


class AuthenticationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recruiter1",
            email="recruiter@example.test",
            password="Strong-Test-Password-123!",
            role=UserRole.RECRUITER,
            first_name="Test",
            last_name="Recruiter",
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("accounts:me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_obtain_jwt_pair(self):
        response = self.client.post(
            reverse("accounts:token_obtain_pair"),
            {"username": "recruiter1", "password": "Strong-Test-Password-123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_authenticated_user_can_read_own_profile(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("accounts:me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)
        self.assertEqual(response.data["role"], UserRole.RECRUITER)
        self.assertEqual(response.data["email"], self.user.email)

    def test_refresh_token_endpoint(self):
        token_response = self.client.post(
            reverse("accounts:token_obtain_pair"),
            {"username": "recruiter1", "password": "Strong-Test-Password-123!"},
            format="json",
        )
        response = self.client.post(
            reverse("accounts:token_refresh"),
            {"refresh": token_response.data["refresh"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)


class RecruiterCreationTests(APITestCase):
    PAYLOAD = {"username": "newrec", "email": "new.rec@example.test", "first_name": "New", "last_name": "Rec",
               "password": "Strong-Test-Password-123!", "password_confirm": "Strong-Test-Password-123!", "role": "ADMIN"}

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user("adm", "adm@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("mgr", "mgr@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER)
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.url = reverse("accounts:users")

    def test_admin_and_manager_can_add_a_recruiter_and_role_is_forced(self):
        for actor in (self.admin, self.manager):
            self.client.force_authenticate(actor)
            payload = {**self.PAYLOAD, "username": f"u{actor.pk}", "email": f"u{actor.pk}@example.test"}
            response = self.client.post(self.url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            self.assertEqual(response.data["role"], UserRole.RECRUITER)  # "ADMIN" in the payload is ignored
            self.assertNotIn("password", response.data)
            self.assertEqual(response.data["job_title"], "HR Recruiter")
            created = User.objects.get(username=payload["username"])
            self.assertTrue(created.check_password(self.PAYLOAD["password"]))
        from audit.models import AuditEvent
        self.assertEqual(AuditEvent.objects.filter(action="RECRUITER_CREATED").count(), 2)

    def test_recruiter_cannot_add_users(self):
        self.client.force_authenticate(self.recruiter)
        self.assertEqual(self.client.post(self.url, self.PAYLOAD, format="json").status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_email_username_and_weak_password_are_rejected(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.url, {**self.PAYLOAD, "email": "REC@example.test", "username": "REC", "password": "123"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(r.data), {"username", "email"})
        r = self.client.post(self.url, {**self.PAYLOAD, "password": "123", "password_confirm": "123"}, format="json")
        self.assertIn("password", r.data)

    def test_password_confirmation_must_match(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.url, {**self.PAYLOAD, "password_confirm": "Different-Password-456!"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", r.data)


class PasswordChangeTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user("rec", "rec@example.test", "Old-Password-123!", role=UserRole.RECRUITER)
        self.url = reverse("accounts:password-change")
        self.good = {"current_password": "Old-Password-123!", "new_password": "New-Strong-Pass-456!", "new_password_confirm": "New-Strong-Pass-456!"}

    def test_requires_authentication(self):
        self.assertEqual(self.client.post(self.url, self.good, format="json").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_changes_own_password(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(self.url, self.good, format="json").status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-Strong-Pass-456!"))

    def test_wrong_current_mismatch_weak_and_unchanged_are_rejected(self):
        self.client.force_authenticate(self.user)
        for change, field in (
            ({"current_password": "wrong"}, "current_password"),
            ({"new_password_confirm": "Other-Pass-789!"}, "new_password_confirm"),
            ({"new_password": "123", "new_password_confirm": "123"}, "new_password"),
            ({"new_password": "Old-Password-123!", "new_password_confirm": "Old-Password-123!"}, "new_password"),
        ):
            r = self.client.post(self.url, {**self.good, **change}, format="json")
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(field, r.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Password-123!"))


class RecruiterManagementTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user("adm", "adm@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("mgr", "mgr@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER)
        self.rec = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.RECRUITER, first_name="Rae")
        self.url = reverse("accounts:user-detail", args=[self.rec.pk])

    def test_admin_and_manager_edit_but_username_and_role_are_fixed(self):
        for actor in (self.admin, self.manager):
            self.client.force_authenticate(actor)
            r = self.client.patch(self.url, {"first_name": f"Rae{actor.pk}", "job_title": "Interviewer", "role": "ADMIN", "username": "x"}, format="json")
            self.assertEqual(r.status_code, 200, r.data)
        self.rec.refresh_from_db()
        self.assertEqual((self.rec.role, self.rec.username, self.rec.job_title), (UserRole.RECRUITER, "rec", "Interviewer"))

    def test_email_must_stay_unique(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(self.url, {"email": "MGR@example.test"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)

    def test_only_admin_toggles_active_and_deactivated_user_cannot_sign_in(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(self.url, {"is_active": False}, format="json").status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(self.url, {"is_active": False}, format="json").status_code, 200)
        login = self.client.post(reverse("accounts:token_obtain_pair"), {"username": "rec", "password": "Pass-12345!"}, format="json")
        self.assertEqual(login.status_code, 401)
        listed = self.client.get(reverse("accounts:users"), {"role": "RECRUITER"}).data
        self.assertEqual(listed, [])
        listed = self.client.get(reverse("accounts:users"), {"role": "RECRUITER", "include_inactive": "1"}).data
        self.assertEqual([u["is_active"] for u in listed], [False])

    def test_delete_unused_account_but_not_one_with_history(self):
        from audit.models import AuditEvent
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.client.force_authenticate(self.admin)
        used = User.objects.create_user("used", "used@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        AuditEvent.objects.create(actor=used, action="X", entity_type="user", entity_id="1")
        self.assertEqual(self.client.delete(reverse("accounts:user-detail", args=[used.pk])).status_code, 409)
        self.assertTrue(User.objects.filter(pk=used.pk).exists())
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.rec.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="RECRUITER_DELETED").exists())

    def test_only_recruiter_accounts_are_managed(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(reverse("accounts:user-detail", args=[self.manager.pk]), {"first_name": "X"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(reverse("accounts:user-detail", args=[self.admin.pk])).status_code, 400)


from django.core import mail as _mail  # noqa: E402
from django.test import override_settings as _override  # noqa: E402


@_override(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_BASE_URL="https://hr.example.test")
class ForgotPasswordTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.users = {role: User.objects.create_user(role.lower(), f"{role.lower()}@example.test", "Old-Password-123!", role=role)
                      for role in (UserRole.ADMIN, UserRole.HIRING_MANAGER, UserRole.RECRUITER)}

    def request_link(self, email):
        self.client.post(reverse("accounts:password-forgot"), {"email": email}, format="json")
        body = _mail.outbox[-1].body
        link = next(line for line in body.splitlines() if line.startswith("https://hr.example.test/reset-password"))
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(link).query)
        return q["uid"][0], q["token"][0]

    def test_every_role_can_reset_with_the_emailed_link_and_the_link_works_once(self):
        for role, user in self.users.items():
            uid, token = self.request_link(user.email)
            payload = {"uid": uid, "token": token, "new_password": "Brand-New-Pass-789!", "new_password_confirm": "Brand-New-Pass-789!"}
            self.assertEqual(self.client.post(reverse("accounts:password-reset"), payload, format="json").status_code, 200, role)
            user.refresh_from_db()
            self.assertTrue(user.check_password("Brand-New-Pass-789!"))
            again = self.client.post(reverse("accounts:password-reset"), {**payload, "new_password": "Another-Pass-321!", "new_password_confirm": "Another-Pass-321!"}, format="json")
            self.assertEqual(again.status_code, 400)  # used link
            self.assertTrue(self.client.post(reverse("accounts:token_obtain_pair"), {"username": user.username, "password": "Brand-New-Pass-789!"}, format="json").status_code == 200)

    def test_unknown_and_inactive_emails_get_the_same_answer_and_no_email(self):
        User.objects.filter(role=UserRole.RECRUITER).update(is_active=False)
        known = self.client.post(reverse("accounts:password-forgot"), {"email": "admin@example.test"}, format="json")
        unknown = self.client.post(reverse("accounts:password-forgot"), {"email": "nobody@example.test"}, format="json")
        inactive = self.client.post(reverse("accounts:password-forgot"), {"email": "recruiter@example.test"}, format="json")
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(known.data, inactive.data)
        self.assertEqual(len(_mail.outbox), 1)

    def test_bad_token_mismatch_and_weak_password_are_rejected(self):
        uid, token = self.request_link("admin@example.test")
        url = reverse("accounts:password-reset")
        good = {"uid": uid, "token": token, "new_password": "Brand-New-Pass-789!", "new_password_confirm": "Brand-New-Pass-789!"}
        self.assertEqual(self.client.post(url, {**good, "token": "bad-token"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {**good, "new_password_confirm": "Different-Pass-1!"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {**good, "new_password": "123", "new_password_confirm": "123"}, format="json").status_code, 400)
        self.users[UserRole.ADMIN].refresh_from_db()
        self.assertTrue(self.users[UserRole.ADMIN].check_password("Old-Password-123!"))
        self.assertEqual(self.client.post(url, good, format="json").status_code, 200)

    def test_requests_are_throttled(self):
        url = reverse("accounts:password-forgot")
        codes = [self.client.post(url, {"email": "nobody@example.test"}, format="json").status_code for _ in range(12)]
        self.assertIn(429, codes)
