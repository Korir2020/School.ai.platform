from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LearningClaimThrottle(AnonRateThrottle):
    scope = "learning_claim"


class LearningGuardianThrottle(UserRateThrottle):
    scope = "learning_guardian_action"


class LearningInvitationAdminThrottle(UserRateThrottle):
    scope = "learning_invitation_admin"


class LearningProfileThrottle(UserRateThrottle):
    scope = "learning_profile"


class LearningLifecycleThrottle(UserRateThrottle):
    scope = "learning_account_lifecycle"


class LearningCatalogThrottle(UserRateThrottle):
    scope = "learning_catalog"


class LearningActivityThrottle(UserRateThrottle):
    scope = "learning_activity"


class LearningQuizThrottle(UserRateThrottle):
    scope = "learning_quiz"


class LearningRecommendationThrottle(UserRateThrottle):
    scope = "learning_recommendation"


class LearningContentThrottle(UserRateThrottle):
    scope = "learning_content"


class LearningAssetThrottle(UserRateThrottle):
    scope = "learning_asset"
