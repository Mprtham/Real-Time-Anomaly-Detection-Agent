from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redpanda_brokers:          str   = "localhost:9092"
    groq_api_key:              str   = ""
    slack_webhook_url:         str   = ""
    anomaly_z_threshold:       float = 3.0
    triage_confidence_cutoff:  float = 0.4
    escalation_confidence:     float = 0.8
    alert_cooldown_minutes:    float = 10.0
    api_port:                  int   = 8000
    cors_origins:              str   = '["http://localhost:3000"]'

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
