"""Importa todos los modelos para que Alembic los vea en target_metadata."""

from src.adapters.postgres.models.audit_log import AuditLogModel
from src.adapters.postgres.models.borrador import BorradorModel
from src.adapters.postgres.models.chat_privado import ChatPrivadoModel
from src.adapters.postgres.models.configuracion_rag import ConfiguracionRAGModel
from src.adapters.postgres.models.consulta_historial import ConsultaHistorialModel
from src.adapters.postgres.models.documento_chat import DocumentoChatModel
from src.adapters.postgres.models.espacio_trabajo import EspacioTrabajoModel
from src.adapters.postgres.models.expediente import ExpedienteModel
from src.adapters.postgres.models.formato_documento import FormatoDocumentoModel
from src.adapters.postgres.models.fragmento import FragmentoModel
from src.adapters.postgres.models.intentos_login import IntentosLoginModel
from src.adapters.postgres.models.mensaje_chat import MensajeChatModel
from src.adapters.postgres.models.modulo import ModuloModel
from src.adapters.postgres.models.norma import NormaModel
from src.adapters.postgres.models.obra import ObraModel
from src.adapters.postgres.models.obra_origen import ObraOrigenModel
from src.adapters.postgres.models.recomendacion_doctrina import RecomendacionDoctrinaModel
from src.adapters.postgres.models.refresh_token import RefreshTokenModel
from src.adapters.postgres.models.usuario import UsuarioModel
from src.adapters.postgres.models.usuario_modulo_permiso import UsuarioModuloPermisoModel

__all__ = [
    "AuditLogModel",
    "BorradorModel",
    "ChatPrivadoModel",
    "ConfiguracionRAGModel",
    "ConsultaHistorialModel",
    "DocumentoChatModel",
    "EspacioTrabajoModel",
    "ExpedienteModel",
    "FormatoDocumentoModel",
    "FragmentoModel",
    "IntentosLoginModel",
    "MensajeChatModel",
    "ModuloModel",
    "NormaModel",
    "ObraModel",
    "ObraOrigenModel",
    "RecomendacionDoctrinaModel",
    "RefreshTokenModel",
    "UsuarioModel",
    "UsuarioModuloPermisoModel",
]
