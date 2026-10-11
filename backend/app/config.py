from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    mst_rpc_url: str = "https://testnetrpc.mstblockchain.com"
    mst_explorer_url: str = "https://testnet.mstscan.com"
    escrow_address: str = ""
    verifier_private_key: str = ""
    indexer_start_block: int = 0
    run_indexer: bool = True
    gemini_api_key: str = ""        # server-side only: never expose to the browser
    gemini_model: str = "gemini-flash-latest"
    ai_calls_per_hour: int = 30
    env: str = "development"        # "production" hides /docs
    require_verified_email: bool = True
    max_upload_mb: int = 25         # delivered zip files
    max_proof_mb: int = 5
    github_token: str = ""
    web_origins: str = "http://localhost:3000,http://admin.localhost:3000"
    sandbox_runtime: str = ""  # e.g. "runsc" (gVisor) for stronger isolation
    sandbox_images: str = "python:3.12-slim,node:20-slim"
    max_runs_per_milestone: int = 5
    symbol: str = "MST"
    run_keeper: bool = True
    resend_api_key: str = ""        # optional: email notifications via Resend
    email_from: str = "ProofPay <notifications@example.com>"
    app_url: str = "http://localhost:3000"


settings = Settings()
