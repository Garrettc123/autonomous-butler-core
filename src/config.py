"""Configuration for Autonomous Butler Core."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    environment: str = "development"
    log_level: str = "INFO"

    # AI Models
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # GitHub Integration
    github_token: str = ""
    github_username: str = ""
    github_org: str = ""

    # Linear Project Management
    linear_api_key: str = ""
    linear_team_id: str = ""

    # Stripe Revenue
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_usage_price_id: str = ""
    stripe_acquisition_price_id: str = ""

    # Revenue streams: comma-separated stream ids, or "all" for every stream.
    # Valid ids: acquisition, subscriptions, usage_based, one_time, dunning,
    # expansion
    revenue_streams: str = "all"

    # Customer acquisition
    # Comma-separated keywords describing the ideal customer profile; used to
    # search for leads and to score how well a discovered account fits.
    icp_keywords: str = ""
    lead_qualify_score: int = 55
    clearbit_api_key: str = ""
    hunter_api_key: str = ""

    # Infrastructure
    kubernetes_config_path: str = "/root/.kube/config"
    kubernetes_context: str = "production"

    # Event Mesh
    kafka_brokers: str = ""
    kafka_consumer_group: str = "autonomous-butler"
    redis_url: str = ""

    # Database
    postgres_url: str = ""

    # Monitoring
    prometheus_url: str = ""
    slack_webhook_url: str = ""
    pagerduty_api_key: str = ""

    # Agent configuration
    auto_deploy_enabled: bool = True
    auto_heal_enabled: bool = True
    auto_scale_enabled: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
