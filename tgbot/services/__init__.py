from database import user_repo, tariff_repo, promo_repo, channel_repo, stats_repo, payment_repo, external_sub_repo, external_config_repo
from loader import marzban_client

from .subscription_service import SubscriptionService
from .referral_service import ReferralService
from .promo_code_service import PromoCodeService
from .user_service import UserService
from .profile_service import ProfileService
from .admin_stats_service import AdminStatsService
from .payment_service import PaymentService
from .support_service import SupportService
from .external_vpn_service import ExternalVpnService

subscription_service = SubscriptionService(user_repo, marzban_client)
referral_service = ReferralService(user_repo, subscription_service)
promo_service = PromoCodeService(promo_repo, user_repo)
user_service = UserService(user_repo, stats_repo)
profile_service = ProfileService(user_repo, marzban_client)
admin_stats_service = AdminStatsService(stats_repo, marzban_client, payment_repo)
payment_service = PaymentService(subscription_service, referral_service, user_repo, tariff_repo, payment_repo)
support_service = SupportService(user_repo)
external_vpn_service = ExternalVpnService(external_sub_repo, external_config_repo)
