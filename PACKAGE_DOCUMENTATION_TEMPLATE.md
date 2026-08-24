# Package Documentation Template

**For**: Trigerr 12-Repo Documentation Project  
**Version**: 1.0  
**Created**: 2025-06-20  
**Purpose**: Standardized structure for `trigerr_package_*.md` files across all repositories

---

## Overview

This template provides a standardized structure for documenting each repository in the Trigerr project. By following this format, all 12 repos will:
- Be self-contained (readable standalone)
- Be mergeable (combine into a single "bible")
- Have consistent cross-linking
- Minimize duplication while maintaining clarity

**Expected File Naming**:
- Repo: `trigerr-core` → File: `trigerr_package_core.md`
- Repo: `trigerr-data-api` → File: `trigerr_package_data_api.md`
- Repo: `trigerr-orders-service` → File: `trigerr_package_orders.md`
- etc.

**File Size Guideline**: 1,500–3,000 lines (comprehensive but readable). Use `#offset` comments for long sections.

---

## Template Structure

Copy this template and fill in each section. Sections marked **[CORE]** are mandatory; **[OPT]** are optional based on repo type.

```markdown
# [Repo Name] Package Documentation

**Version**: X.Y.Z  
**Author**: [Author Name]  
**Language/Stack**: [Python/Go/Node.js]  
**Role in Trigerr**: [Brief role, e.g., "Data fetching service"]

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module/File Structure](#module-structure)
4. [Public API Reference](#public-api-reference)
5. [Data Models & Conventions](#data-models--conventions)
6. [Configuration](#configuration)
7. [Integration Points](#integration-points)
8. [Core Algorithms](#core-algorithms)
9. [Dependencies](#dependencies)
10. [Development & Distribution](#development--distribution)

---

## Overview [CORE]

**2-3 paragraph summary**:
- What problem does this repo solve?
- What's unique about it?
- How does it fit into the larger Trigerr ecosystem?

**Key Responsibilities**:
- [ ] Responsibility 1
- [ ] Responsibility 2
- [ ] Responsibility 3

**Dependencies on Other Repos** (for cross-linking):
- Depends on: [[trigerr-core]] (for config management)
- Depended on by: [[trigerr-orders-service]] (for order placement)
- Parallel with: [[trigerr-live-data]] (independent services)

**Technology Stack**:
- Language: Python 3.9+
- Framework: FastAPI (if applicable)
- Database: MongoDB, Redis
- External APIs: (list any)

---

## Architecture [CORE]

### Design Principles

- Principle 1 with justification
- Principle 2 with justification
- etc.

### High-Level Data Flow

```
┌─────────────┐
│  Client     │
└──────┬──────┘
       │
┌──────▼──────────────┐
│  Public API Layer   │
└──────┬──────────────┘
       │
┌──────▼──────────────┐
│  Business Logic     │
└──────┬──────────────┘
       │
┌──────▼──────────────┐
│  Data/External APIs │
└─────────────────────┘
```

### Key Architectural Patterns

1. **Pattern Name**: Description + rationale + trade-offs
2. **Pattern Name**: Description + rationale + trade-offs

---

## Module Structure [CORE]

**Directory tree**:
```
repo-name/
├── src/                        # Main source code
│   ├── module_a.py             # Purpose: ...
│   ├── module_b.py             # Purpose: ...
│   └── submodule/
│       └── module_c.py         # Purpose: ...
├── tests/                      # Test suite
├── examples/                   # Example scripts
├── docs/                       # Internal documentation
└── README.md
```

**File Purpose Table**:

| File | Lines | Purpose |
|------|-------|---------|
| `module_a.py` | ~200 | Core logic for feature X |
| `module_b.py` | ~150 | Data transformations |
| `module_c.py` | ~100 | Utilities and helpers |

**Module Relationships**:
```
module_a → module_b → module_c
           └─────────→ external_api
```

---

## Public API Reference [CORE]

### Configuration Functions

```python
import package_name

# Set configuration
package_name.set_option("key", "value")

# Get configuration
value = package_name.get_config("key")
```

### Core Functions

#### Function Group 1

```python
from package_name import function_1

# Description and purpose
result = function_1(
    param1,           # Type and description
    param2=default,   # Type and description
)
# Returns: Type and description of return value
```

**Parameters**:
- `param1` (str): Description
- `param2` (int): Description

**Returns**: 
- (dict): Description of return

**Raises**:
- `ValueError`: Condition when raised
- `ConnectionError`: Condition when raised

**Examples**:
```python
# Example 1: Basic usage
result = function_1("input")
print(result)

# Example 2: Advanced usage
result = function_1("input", param2=42)
```

#### Function Group 2

[Similar structure...]

### [OPT] REST API Endpoints

```
POST /endpoint/path
Content-Type: application/json

Request:
{
  "field1": "value1",
  "field2": 123
}

Response (200):
{
  "status": "success",
  "data": {...}
}

Response (400):
{
  "status": "error",
  "message": "Error description"
}
```

---

## Data Models & Conventions [CORE]

### Primary Data Structures

#### Model 1: Entity Name

```python
{
    "id": str,              # Unique identifier
    "name": str,            # Display name
    "created_at": datetime, # Creation timestamp
    "status": str,          # One of: ACTIVE, INACTIVE, ARCHIVED
    # ... other fields
}
```

**Validation Rules**:
- `id`: Non-empty, unique across system
- `name`: Max 255 chars, alphanumeric + spaces
- `status`: Enum values only

**Serialization**: JSON (CamelCase for API, snake_case for internal)

#### Model 2: [Another Entity]

[Similar structure...]

### Naming Conventions

| Concept | Format | Example |
|---------|--------|---------|
| Variables | snake_case | `user_id`, `order_status` |
| Classes | PascalCase | `OrderService`, `DataFetcher` |
| Constants | UPPER_CASE | `MAX_RETRIES`, `API_TIMEOUT` |
| Private methods | _leading_underscore | `_validate_input()` |
| DB fields | snake_case | `user_id`, `created_at` |
| API fields | camelCase | `userId`, `createdAt` |

### Error Response Format

```python
{
    "error": {
        "code": "ERROR_CODE",      # Machine-readable code
        "message": "Human message", # User-friendly message
        "details": {...}           # Additional context
    }
}
```

---

## Configuration [CORE]

### Configuration Options

**Environment Variables**:

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `DATABASE_URL` | str | `localhost:27017` | MongoDB connection |
| `REDIS_URL` | str | `localhost:6379` | Redis cache |
| `API_KEY` | str | None (required) | Authentication token |
| `DEBUG_MODE` | bool | False | Enable verbose logging |
| `TIMEOUT_SECONDS` | int | 30 | Request timeout |

**Runtime Configuration** (if applicable):

```python
from package_name import config

# Get
value = config.get("key")

# Set
config.set("key", value)

# Load from file
config.load("path/to/config.yml")
```

### Defaults and Overrides

- Defaults: Defined in `config.py` or `.env.example`
- Environment variables: Override defaults at runtime
- Local overrides: `config.local.yml` (git-ignored)

---

## Integration Points [CORE]

### External Services

**Service 1: [Name]** (e.g., Data API, Message Queue)
- **URL**: https://api.example.com/v1/
- **Authentication**: API Key in `Authorization` header
- **Endpoints**: List key endpoints
- **Response Format**: JSON
- **Error Handling**: Retry on 5xx, fail-fast on 4xx

**Service 2: [Name]**
- [Similar structure...]

### Broker/Exchange Integrations

- **Broker Name**: NSE, BSE, Zerodha, etc.
- **Integration Type**: REST API, WebSocket, FIX
- **Credentials**: API key + secret stored securely
- **Rate Limits**: Requests per second

### Internal Service Dependencies

- **Depends on**: [[trigerr-core]] → config management, logging
- **Depended on by**: [[trigerr-live-data]] → data processing
- **Event Streams**: Publishes `order_placed`, `position_updated` events

### Authentication & Security

- **API Key Validation**: Checked on every request
- **Encryption**: TLS for data in transit, at-rest via service
- **Access Control**: Role-based (admin, trader, viewer)
- **Audit Logging**: All sensitive operations logged

---

## Core Algorithms [OPT]

### Algorithm 1: [Name]

**Purpose**: What problem does it solve?

**Input**:
- Param 1: Description
- Param 2: Description

**Output**:
- Result: Description

**Algorithm** (pseudocode or step-by-step):
```
1. Initialize state
2. For each item in input:
   a. Process item
   b. Update state
3. Return final result
```

**Complexity**:
- Time: O(n log n) where n = input size
- Space: O(n)

**Example**:
```python
result = algorithm_name(input_data)
```

### Algorithm 2: [Name]

[Similar structure...]

---

## Dependencies [CORE]

### Runtime Dependencies

```
dependency1>=1.2.3    # Purpose: data processing
dependency2~=2.0     # Purpose: HTTP client
dependency3          # Purpose: encryption
```

**Total Size**: ~50 MB

**Compatibility**:
- Python: 3.9 to 3.12
- OS: Linux, macOS, Windows
- Architecture: x86_64, ARM64

### Development Dependencies

```
pytest>=7.0          # Testing
pytest-cov           # Coverage reporting
black                # Code formatting
mypy                 # Type checking
```

### Optional Dependencies

```
pandas-compat[excel]  # For Excel export (optional)
plotly                # For visualization (optional)
```

### Vendored Dependencies

List any bundled libraries (e.g., pandas_ta in trigerr-core)

---

## Development & Distribution [CORE]

### Local Setup

```bash
# Clone and install
git clone https://github.com/trigerr/repo-name.git
cd repo-name
pip install -e .

# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Build docs
make docs
```

### Running Examples

```bash
# Example 1
python examples/example1.py

# Example 2
python examples/example2.py --verbose
```

### Testing

**Test Structure**:
```
tests/
├── unit/
│   ├── test_module_a.py
│   ├── test_module_b.py
│   └── ...
├── integration/
│   ├── test_api.py
│   ├── test_database.py
│   └── ...
└── fixtures/
    ├── sample_data.json
    └── mock_responses.py
```

**Running Tests**:
```bash
# All tests
pytest

# Specific test file
pytest tests/unit/test_module_a.py

# With coverage
pytest --cov=src

# Only integration tests
pytest tests/integration/
```

### Building & Distribution

```bash
# Build wheel and source distribution
python setup.py sdist bdist_wheel

# Upload to PyPI (if public)
twine upload dist/*

# Or to private registry
pip install twine
twine upload -r private-registry dist/*
```

### Version Management

- **Versioning Scheme**: Semantic Versioning (MAJOR.MINOR.PATCH)
- **Version File**: `src/__init__.py` or `setup.py`
- **Release Process**:
  1. Update version in source
  2. Tag commit: `git tag v1.2.3`
  3. Push tag: `git push origin v1.2.3`
  4. Build and upload to PyPI

### Deployment

**Staging Environment**:
```bash
git checkout staging
pip install -r requirements.txt
python -m pytest
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

**Production Environment**:
```bash
# Via Docker
docker build -t repo-name:latest .
docker push registry.example.com/repo-name:latest
docker pull registry.example.com/repo-name:latest
docker run -d --name repo-name -e API_KEY=xxx repo-name:latest
```

---

## [OPT] Database Schema

### Collections/Tables

#### Collection: orders

| Field | Type | Indexed | Purpose |
|-------|------|---------|---------|
| `_id` | ObjectId | Yes | Primary key |
| `user_id` | str | Yes | User reference |
| `symbol` | str | Yes | Trading symbol |
| `quantity` | int | No | Order quantity |
| `status` | str | Yes | PENDING, FILLED, REJECTED |
| `created_at` | datetime | Yes | Creation timestamp |

**Indexes**:
- `user_id + created_at` (compound): Speed up user order history queries
- `symbol + status`: Speed up market filtering

#### Collection: [Other collection]

[Similar structure...]

---

## [OPT] Common Use Cases

### Use Case 1: [Scenario]

**Goal**: What the user wants to accomplish

**Steps**:
1. Step 1 with code
2. Step 2 with code
3. Step 3 with code

**Code Example**:
```python
# Minimal working example
from package_name import function1, function2

data = function1("input")
result = function2(data)
print(result)
```

### Use Case 2: [Scenario]

[Similar structure...]

---

## [OPT] Troubleshooting

### Issue: [Common Problem]

**Symptoms**: What the user observes

**Root Cause**: Why it happens

**Solutions**:
1. Check [X] (e.g., API key validity)
2. Verify [Y] (e.g., database connectivity)
3. Try [Z] (e.g., increase timeout)

**Debug Commands**:
```bash
# Check service health
curl -X GET http://localhost:8000/health

# View logs
tail -f logs/app.log

# Test API endpoint
curl -X POST http://localhost:8000/api/test \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"field": "value"}'
```

### Issue: [Another Common Problem]

[Similar structure...]

---

## [OPT] Performance & Scaling

### Benchmarks

**Operation** | **Latency** | **Throughput**
---|---|---
Fetch 100 records | 50ms | 20k req/s
Process order | 100ms | 10k req/s
Calculate indicators | 200ms | 5k req/s

### Optimization Tips

- Cache frequently accessed data in Redis
- Use bulk operations for batch inserts
- Index database fields that are filtered/sorted
- Profile code with `cProfile` to identify bottlenecks

### Scaling Strategies

- **Horizontal**: Add more service instances behind load balancer
- **Vertical**: Increase CPU/memory resources
- **Database**: Shard by `user_id` or time ranges
- **Caching**: Redis for hot data, CDN for static assets

---

## Key Design Decisions

### Decision 1: [Title]

**Decision**: What was decided?

**Rationale**: Why this choice?

**Alternatives Considered**: What other options existed?

**Trade-offs**: What's the downside?

**Revision History**: Has this been revisited? When?

### Decision 2: [Title]

[Similar structure...]

---

## Future Development Notes

- [ ] Feature or improvement 1
- [ ] Feature or improvement 2
- [ ] Optimization opportunity
- [ ] Known limitation to address

---

## Version History

- **1.0.0** (Current): Initial production release
  - Full feature set
  - Database v1 schema
  - API v1 endpoints

- **0.9.0** (Beta): Pre-release
  - Testing phase features

---

## Contact & Support

- **Author**: [Name]
- **Slack Channel**: #trigerr-repo-name
- **On-Call Runbook**: [Link to wiki]
- **Issue Tracker**: https://github.com/trigerr/repo-name/issues

---

## License

MIT License — See LICENSE file in repository.

```

---

## Guidance by Repo Type

### For Backend Services (API Servers)

**Emphasize**:
- REST/GraphQL endpoint documentation
- Database schema and indexes
- Authentication/authorization model
- Deployment (Docker, Kubernetes, load balancing)
- Performance benchmarks and scaling strategy

**Example Repos**:
- trigerr-data-api
- trigerr-orders-service
- trigerr-broker-integration

### For Libraries (Python/JavaScript)

**Emphasize**:
- Public API reference with examples
- Data models and type definitions
- Core algorithms and complexity
- Dependency management
- Installation and usage patterns

**Example Repos**:
- trigerr-core (current package)
- trigerr-ta-library
- trigerr-client-sdk

### For Databases/Infrastructure

**Emphasize**:
- Schema design and relationships
- Backup/recovery procedures
- Performance tuning
- Monitoring and alerting
- Migration processes

**Example Repos**:
- trigerr-datastore
- trigerr-cache-layer

### For Tools/Utilities

**Emphasize**:
- Command-line interface and flags
- Configuration files
- Input/output formats
- Common workflows
- Troubleshooting

**Example Repos**:
- trigerr-cli
- trigerr-backtest-runner

---

## Best Practices for Multi-Repo Documentation

### 1. Cross-Linking

**Pattern**: Use markdown link syntax with `[[repo-name:section]]` for later processing.

```markdown
See [[trigerr-data-api#endpoints]] for available endpoints.
Depends on [[trigerr-core#authentication]] for API key validation.
```

**In Combined Bible**: A script converts these to proper markdown links.

### 2. Avoiding Duplication

**Strategy**: Document once, reference often.

- **Shared Concepts**: Define in central document (e.g., ARCHITECTURE_OVERVIEW.md)
  - Example: Authentication flow, error response format
- **Common Utilities**: Link to library docs, don't duplicate
- **Standard Tables**: Create once in central place, reference by row

**Example**:
```markdown
For error response format, see [[ARCHITECTURE_OVERVIEW#error-handling]].
For available brokers, see [[BROKERS.md]].
```

### 3. Version Alignment

- Include repo version in header (e.g., `**Version**: 0.1.4.6.3`)
- Include date of last update (e.g., `**Updated**: 2025-06-20`)
- In combined bible, create version compatibility matrix

### 4. Readability for Offline Access

- All docs should be readable as standalone Markdown
- Don't rely on cross-linking for essential info
- Self-contained examples that work without other repos

### 5. Consistency Across Repos

**Enforce**:
- Same heading structure (## Overview, ## Architecture, etc.)
- Same table formats (data types, naming conventions)
- Same code block language (python, bash, sql)
- Same terminology (e.g., always "Order" not "Trade" or "Position")

---

## Generating the Combined "Bible"

### Script Outline (Python)

```python
import os
import glob
import re

def combine_docs():
    """Combine all trigerr_package_*.md into single bible."""
    
    # 1. Start with architecture overview
    bible = read_file("ARCHITECTURE_OVERVIEW.md")
    bible += "\n\n---\n\n"
    
    # 2. For each repo file in order
    for doc_file in sorted(glob.glob("trigerr_package_*.md")):
        content = read_file(doc_file)
        
        # 3. Adjust heading levels (+1 for nested)
        content = adjust_headings(content, offset=1)
        
        # 4. Resolve cross-refs
        content = resolve_cross_refs(content, bible)
        
        # 5. Append to bible
        bible += content + "\n\n---\n\n"
    
    # 6. Generate master TOC
    toc = generate_toc(bible)
    bible = toc + "\n\n" + bible
    
    # 7. Export
    write_file("TRIGERR_COMPLETE_BIBLE.md", bible)
    export_pdf("TRIGERR_COMPLETE_BIBLE.pdf", bible)
    print(f"Generated combined bible: {len(bible)} chars, {bible.count(chr(10))} lines")

def resolve_cross_refs(content, bible):
    """Replace [[repo-name:section]] with proper links."""
    pattern = r'\[\[([\w-]+)#([\w-]+)\]\]'
    
    def replacer(match):
        repo, section = match.groups()
        # Find section in bible and get link
        return f"[{repo}#{section}](#{repo.lower()}-{section.lower()})"
    
    return re.sub(pattern, replacer, content)

if __name__ == "__main__":
    combine_docs()
```

---

## Checklist for Creating Documentation

- [ ] Filled all [CORE] sections
- [ ] Filled relevant [OPT] sections for repo type
- [ ] Provided at least 3 code examples
- [ ] Documented all public functions
- [ ] Included data model schema
- [ ] Listed all dependencies with versions
- [ ] Added cross-links to related repos
- [ ] Ran spell-check and grammar review
- [ ] Tested code examples (copy-paste and run)
- [ ] Got review from repo maintainer

---

## Questions & Adjustments

**Q: Should I include code comments in this doc?**  
A: No — reference actual code line numbers instead. This doc is for **what** and **why**, comments are for **how**.

**Q: What if my repo is much simpler/more complex?**  
A: Adjust section sizes to match. Simple library might be 1,000 lines; complex service might be 4,000+. Aim for complete coverage.

**Q: How often should I update this?**  
A: After major features (new endpoints, breaking changes). Minor updates (bug fixes) don't require doc changes.

**Q: Can I use this for internal wikis or Notion?**  
A: Yes — export to HTML/PDF, or keep as git-tracked Markdown. Either works for the combined bible.

---

## Support

- Questions about this template? Contact documentation lead.
- Finished documentation for your repo? Submit PR with `trigerr_package_yourrepo.md`
- Need help with cross-repo links? See the script example above.
