"""Import all models to register the complete shared migration metadata."""
from docweave.db.base import Base, Record
from .auth import User, AuthFlow, AuthSession, AuthRateLimit
from .workspaces import Workspace, Membership, Invitation
from .projects import Project, DocumentationRequest
from .collections import Collection, CollectionGrant, Processor, ProjectProcessorApproval, CollectionProcessorApproval
from .budget import ProviderProfile, WorkspaceAllowance, CostReservation, CompatibilityRequest, CompatibilityOperation
from .ingestion import DocumentationSelection, Source, Document, DocumentVersion, IngestionJob
from .retrieval import IndexGeneration, DocumentIndex, Chunk
