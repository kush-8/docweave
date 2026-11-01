"""Import all models to register the complete shared migration metadata."""
from docweave.db.base import Base, Record
from .auth import User, AuthFlow, AuthSession, AuthRateLimit
from .workspaces import Workspace, Membership, Invitation
from .projects import Project, DocumentationRequest
from .catalog import PublicCatalogRevision, ProjectCatalogSelection
from .collections import Collection, CollectionGrant, Processor, ProjectProcessorApproval, CollectionProcessorApproval
from .budget import ProviderProfile, WorkspaceAllowance, CostReservation, CompatibilityRequest, CompatibilityOperation
from .ingestion import DocumentationSelection, Source, Document, DocumentVersion, IngestionJob
from .retrieval import IndexGeneration, DocumentIndex, Chunk

from .conversations import Conversation, Turn, PersonalJob

from .guardrails import DocumentAssessment

from .catalog_jobs import CatalogJob

from .budget import PersonalProviderCall

from .private_index_jobs import PrivateIndexJob
