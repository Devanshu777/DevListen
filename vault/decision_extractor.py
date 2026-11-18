"""
Autonomous Decision & Entity Extractor for DevListen.
Analyzes conversational transcripts in real-time to extract:
- Technical Entities (projects, services, architecture choices, tools)
- Decision Status (ACTIVE, REJECTED, PROPOSED, SUPERSEDED)
- Attribution (Proposed by, Agreed/Decided by)
- Structured summaries and rationales
"""
import re
from typing import Dict, Any, Optional, List
from vault.temporal_graph import TemporalDecisionGraph

# Known software entity keywords to assist entity extraction
TECH_KEYWORDS = {
    "kubernetes", "nginx", "postgresql", "postgres", "redis", "mongodb", "graphql",
    "grpc", "oauth2", "jwt", "ci/cd", "ci-cd", "docker", "kafka", "rabbitmq", "aws",
    "gcp", "azure", "rest", "api gateway", "microservices", "caching", "database",
    "guava", "playwright", "ospf", "pom", "ajax", "semgrep", "dast", "fuzzing"
}

class DecisionExtractor:
    """
    Extracts decisions, architectural choices, and technical agreements
    from conversational utterances and registers them into the Temporal Graph.
    """
    def __init__(self, graph: TemporalDecisionGraph):
        self.graph = graph

    def analyze_utterance(self, text: str, speaker: str, meeting_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Parses a transcribed utterance. If it contains a technical proposal, agreement,
        or rejection, records it into the database and returns the decision metadata.
        """
        if not text or len(text.strip()) < 10:
            return None

        clean_text = text.strip()

        # Pattern 1: Rejection pattern
        # e.g. "Alex proposed using MongoDB, but the architect rejected because we need ACID transactions."
        rej_match = re.search(
            r'(?:(?P<proposer>[A-Z][a-z]+)\s+)?(?:proposed|suggested)\s+(?:using\s+|implementing\s+)?(?P<entity>[\w\s\.-]+?),\s*but\s+(?:the\s+)?(?:I\s+think\s+)?(?P<decider>[A-Za-z]+)?\s+(?:rejected|vetoed|declined)(?:\s+it)?(?:\s+because\s+(?P<reason>.*))?',
            clean_text,
            re.IGNORECASE
        )
        if rej_match:
            proposer = rej_match.group("proposer") or speaker
            entity_raw = rej_match.group("entity").strip()
            decider = rej_match.group("decider") or "Architect"
            reason = rej_match.group("reason") or "Not specified"
            
            entity = self._normalize_entity_name(entity_raw)
            if not entity:
                return None
            summary = f"Rejected {entity} by {decider}: {reason.strip()}"
            
            decision_id = self.graph.record_decision(
                meeting_uuid=meeting_uuid,
                entity_name=entity,
                summary=summary,
                proposed_by=proposer,
                agreed_by=decider,
                status="REJECTED"
            )
            return {
                "decision_id": decision_id,
                "entity": entity,
                "status": "REJECTED",
                "summary": summary,
                "proposed_by": proposer,
                "agreed_by": decider
            }

        # Pattern 2: Adoption / Deployment decision
        # e.g. "We deployed the Kubernetes cluster with an NGINX ingress controller and hooked it up with PostgreSQL and Redis."
        adopt_match = re.search(
            r'(?:we\s+)?(?:deployed|decided\s+to\s+use|agreed\s+on|configured|built)\s+(?:the\s+)?(?P<entity>[\w\s\.-]+?)(?:\s+with\s+(?P<details>.*))?$',
            clean_text,
            re.IGNORECASE
        )
        if adopt_match:
            entity_raw = adopt_match.group("entity").strip()
            details = adopt_match.group("details") or ""
            entity = self._normalize_entity_name(entity_raw)
            if not entity:
                return None
            summary = f"Adopted {entity}"
            if details:
                summary += f" with {details.strip()}"

            decision_id = self.graph.record_decision(
                meeting_uuid=meeting_uuid,
                entity_name=entity,
                summary=summary,
                proposed_by=speaker,
                agreed_by="Team",
                status="ACTIVE"
            )
            return {
                "decision_id": decision_id,
                "entity": entity,
                "status": "ACTIVE",
                "summary": summary,
                "proposed_by": speaker,
                "agreed_by": "Team"
            }

        # Pattern 3: Deprecation & Migration
        # e.g. "We should duplicate/deprecate the REST endpoints and migrate our gRPC services to OAuth2"
        mig_match = re.search(
            r'(?:we\s+should\s+)?(?:deprecate|migrate|replace)\s+(?:the\s+|our\s+)?(?P<old_entity>[\w\s\.-]+?)\s+(?:and\s+migrate\s+(?:our\s+)?|to\s+use\s+)?(?P<new_entity>.*)',
            clean_text,
            re.IGNORECASE
        )
        if mig_match:
            old_raw = mig_match.group("old_entity").strip()
            new_raw = mig_match.group("new_entity").strip()
            entity = self._normalize_entity_name(old_raw)
            if not entity:
                return None
            summary = f"Deprecating {entity} in favor of: {new_raw}"

            decision_id = self.graph.record_decision(
                meeting_uuid=meeting_uuid,
                entity_name=entity,
                summary=summary,
                proposed_by=speaker,
                agreed_by="Team",
                status="ACTIVE"
            )
            return {
                "decision_id": decision_id,
                "entity": entity,
                "status": "ACTIVE",
                "summary": summary,
                "proposed_by": speaker,
                "agreed_by": "Team"
            }

        # Pattern 4: Version Upgrade / Dependency Change
        # e.g. "I think we need to update the POM dependency of Guava from 4.1 to 4.37"
        upg_match = re.search(
            r'(?:we\s+need\s+to\s+|we\s+should\s+|let\'?s\s+|i\s+think\s+we\s+need\s+to\s+)?(?:update|upgrade|bump|change)\s+(?:the\s+)?(?P<entity>[\w\s\.-]+?)\s+(?:from\s+(?P<old_v>[\w\.-]+)\s+)?to\s+(?P<new_v>[\w\.-]+)',
            clean_text,
            re.IGNORECASE
        )
        if upg_match:
            entity_raw = upg_match.group("entity").strip()
            old_v = upg_match.group("old_v") or ""
            new_v = upg_match.group("new_v").strip()
            entity = self._normalize_entity_name(entity_raw)
            if not entity:
                return None
            if old_v:
                summary = f"Upgrade {entity} from {old_v} to {new_v}"
            else:
                summary = f"Update {entity} to {new_v}"

            decision_id = self.graph.record_decision(
                meeting_uuid=meeting_uuid,
                entity_name=entity,
                summary=summary,
                proposed_by=speaker,
                agreed_by="Team",
                status="ACTIVE"
            )
            return {
                "decision_id": decision_id,
                "entity": entity,
                "status": "ACTIVE",
                "summary": summary,
                "proposed_by": speaker,
                "agreed_by": "Team"
            }

        return None

    def _normalize_entity_name(self, raw_entity: str) -> Optional[str]:
        """Extracts the cleanest canonical entity name."""
        clean = re.sub(r'\b(the|a|an|our|all|these|those|this|my|we|you|some|any)\b', '', raw_entity.strip(), flags=re.IGNORECASE).strip()
        if not clean or len(clean) < 3:
            return None

        # Check if pattern is "dependency of/for <sub-package>"
        m_sub = re.search(r'(?:dependency|version|config|package|client|library)\s+(?:of|for)\s+(?P<sub>[\w\.-]+)', clean, re.IGNORECASE)
        if m_sub:
            sub_name = m_sub.group("sub").strip()
            if sub_name.lower() in TECH_KEYWORDS:
                return f"{sub_name.capitalize()} Dependency"
            return f"{sub_name.title()} Dependency"

        words = clean.lower().split()
        for w in words:
            if w in TECH_KEYWORDS:
                if w in ('rest', 'grpc', 'jwt', 'nginx', 'pom', 'ospf', 'ajax'):
                    return w.upper()
                if w in ('oauth2', 'ci/cd', 'ci-cd'):
                    return w.upper()
                return w.capitalize()
        # Fallback to Title Cased string (up to 3 words)
        clean_words = [w for w in clean.split() if len(w) > 2 and w.lower() not in {"the", "system", "thing", "things", "item", "items"}]
        if not clean_words:
            return None
        return " ".join(clean_words[:3]).title()
