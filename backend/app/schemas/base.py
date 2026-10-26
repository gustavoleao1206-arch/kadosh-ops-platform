"""Base dos schemas de entrada: campos desconhecidos são rejeitados e textos têm tamanho máximo.

Isso fecha a porta do "mass assignment" (ex.: staff enviando role=admin num endpoint de perfil) e de
payloads absurdos.
"""

from pydantic import BaseModel, ConfigDict


class InSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_max_length=2000)


class OutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
