"""AWS Secrets Manager variant (production). Scope separation is enforced by IAM: only the executor
task role has ``secretsmanager:GetSecretValue`` on ``adintel/*/*/write``."""

from __future__ import annotations

import json
from typing import Any

from adintel.security.secrets import Credential


class AwsSecretStore:
    def __init__(self) -> None:
        import boto3

        self._sm: Any = boto3.client("secretsmanager")

    def get(self, tenant_id: str, platform: str, scope: str) -> Credential:
        ref = f"adintel/{tenant_id}/{platform}/{scope}"
        value = self._sm.get_secret_value(SecretId=ref)["SecretString"]
        return Credential(tenant_id, platform, scope, ref, json.loads(value))
