from dataclasses import dataclass


@dataclass(frozen=True)
class AwsCredentialsForEnvironment:
    api_key: str
    api_secret: str
    api_region: str