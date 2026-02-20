"""
Justice Canada XML adapter — fetches federal legislation from the official
GitHub repository: github.com/justicecanada/laws-lois-xml

Uses git clone/pull for bulk access, then parses XML files with lxml.
Open Government Licence — Canada.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional
from lxml import etree

from scraper.adapters import register_adapter
from scraper.adapters.base import BaseSourceAdapter, DocumentMetadata, DocumentContent
from utils.logger import logger


REPO_URL = "https://github.com/justicecanada/laws-lois-xml.git"
DEFAULT_CLONE_DIR = Path(__file__).parent.parent.parent / "data" / "federal_xml"


@register_adapter('justice_canada_xml')
class JusticeCanadaXMLAdapter(BaseSourceAdapter):
    """
    Adapter for federal Canadian legislation from Justice Canada's GitHub repo.
    Provides full XML text of all consolidated Acts and Regulations.
    """

    def __init__(self, local_clone_path: str = None, repo_url: str = None, **kwargs):
        self.repo_url = repo_url or REPO_URL
        self.clone_dir = Path(local_clone_path) if local_clone_path else DEFAULT_CLONE_DIR
        self._ensure_repo()

    def get_source_name(self) -> str:
        return "Justice Canada XML (Federal)"

    def get_source_type(self) -> str:
        return "justice_canada_xml"

    def get_jurisdiction(self) -> str:
        return "ca"

    def _ensure_repo(self):
        """Clone or pull the repo."""
        if (self.clone_dir / ".git").exists():
            logger.info(f"Updating Justice Canada XML repo at {self.clone_dir}")
            try:
                subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=str(self.clone_dir),
                    capture_output=True, timeout=120
                )
                logger.info("Git pull completed")
            except Exception as e:
                logger.warning(f"Git pull failed (using existing data): {e}")
        else:
            logger.info(f"Cloning Justice Canada XML repo to {self.clone_dir}")
            self.clone_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", self.repo_url, str(self.clone_dir)],
                    capture_output=True, timeout=300
                )
                logger.info("Git clone completed")
            except Exception as e:
                logger.error(f"Git clone failed: {e}")
                raise

    def _find_xml_files(self, subdir: str = "eng") -> List[Path]:
        """Find all XML files under eng/Acts/ and eng/Regulations/."""
        xml_files = []
        eng_dir = self.clone_dir / subdir
        if not eng_dir.exists():
            logger.warning(f"Directory not found: {eng_dir}")
            return xml_files

        for category_dir in ["acts", "Acts", "regulations", "Regulations"]:
            cat_path = eng_dir / category_dir
            if cat_path.exists():
                for xml_file in sorted(cat_path.glob("*.xml")):
                    xml_files.append(xml_file)
        return xml_files

    def _parse_xml_metadata(self, xml_path: Path) -> Optional[DocumentMetadata]:
        """Extract metadata from an XML file without full parsing."""
        try:
            tree = etree.parse(str(xml_path))
            root = tree.getroot()
            ns_uri = root.nsmap.get(None, '')

            title = None
            for tag in ['LongTitle', 'ShortTitle', 'Title']:
                el = root.find(f'.//{{{ns_uri}}}{tag}') if ns_uri else root.find(f'.//{tag}')
                if el is not None:
                    title = ''.join(el.itertext()).strip()
                    if title:
                        break

            if not title:
                title = xml_path.stem.replace('-', ' ').replace('_', ' ')

            # Determine document type from path (case-insensitive)
            is_regulation = "regulations" in str(xml_path).lower()
            doc_type = "regulation" if is_regulation else "legislation"
            category = "Regulation" if is_regulation else "Legislation"

            # Build a stable source_url (human-readable, not the .xml file)
            rel_path = xml_path.relative_to(self.clone_dir)
            # Remove .xml extension and add trailing slash for the web URL
            # e.g. eng/acts/A-1.xml -> https://laws-lois.justice.gc.ca/eng/acts/A-1/
            url_path = str(rel_path).replace('.xml', '')
            source_url = f"https://laws-lois.justice.gc.ca/{url_path}/"

            # Try to extract citation from filename (e.g., A-1.xml -> A-1)
            citation = xml_path.stem

            return DocumentMetadata(
                source_url=source_url,
                title=title,
                citation=citation,
                jurisdiction_code="ca",
                category=category,
                document_type=doc_type,
                is_active=True,
                metadata={"xml_file": str(rel_path)},
            )
        except Exception as e:
            logger.warning(f"Failed to parse metadata from {xml_path}: {e}")
            return None

    def discover_documents(self, limit: Optional[int] = None) -> List[DocumentMetadata]:
        xml_files = self._find_xml_files("eng")
        logger.info(f"Found {len(xml_files)} XML files in Justice Canada repo")

        docs = []
        for xml_path in xml_files:
            if limit and len(docs) >= limit:
                break
            meta = self._parse_xml_metadata(xml_path)
            if meta:
                docs.append(meta)

        logger.info(f"Discovered {len(docs)} federal documents")
        return docs

    def fetch_document(self, doc_meta: DocumentMetadata) -> Optional[DocumentContent]:
        """Parse full content from a local XML file."""
        try:
            rel_path = doc_meta.metadata.get("xml_file", "")
            xml_path = self.clone_dir / rel_path

            if not xml_path.exists():
                logger.error(f"XML file not found: {xml_path}")
                return None

            tree = etree.parse(str(xml_path))
            root = tree.getroot()

            # Full XML as content_html
            content_html = etree.tostring(root, pretty_print=True, encoding='unicode')

            # Extract plain text from all text nodes
            content_text = self._extract_text(root)

            return DocumentContent(
                source_url=doc_meta.source_url,
                title=doc_meta.title,
                citation=doc_meta.citation,
                content_html=content_html,
                content_text=content_text,
                jurisdiction_code="ca",
                category=doc_meta.category,
                document_type=doc_meta.document_type,
                is_active=True,
                metadata=doc_meta.metadata,
            )
        except Exception as e:
            logger.error(f"Failed to parse {doc_meta.title}: {e}")
            return None

    def _extract_text(self, root) -> str:
        """Extract readable plain text from XML, preserving section structure."""
        parts = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                tag = etree.QName(elem.tag).localname if '}' in str(elem.tag) else elem.tag
                text = elem.text.strip()
                # Add section markers for structure
                if tag in ('Heading', 'TitleText', 'LongTitle', 'ShortTitle', 'Label'):
                    parts.append(f"\n{'=' if tag in ('LongTitle', 'ShortTitle') else '-'} {text}")
                elif tag in ('MarginalNote',):
                    parts.append(f"\n[{text}]")
                elif tag in ('Text', 'FormGroup'):
                    parts.append(text)
            if elem.tail and elem.tail.strip():
                parts.append(elem.tail.strip())
        return '\n'.join(parts)
