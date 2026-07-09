# Standard Entity Selection

Reference for selecting standard entities from `maltego-transforms-std-entities` before creating custom entities.

---

## Import Pattern

All standard entities are imported from `maltego.entities`:

```python
from maltego.entities import Domain, Person, IPv4Address, EmailAddress, Organization
```

Import only what you use.

---

## Entity Categories

### Core / Infrastructure
| Class | When to use |
|-------|-------------|
| `Domain` | Fully-qualified domain name, hostname |
| `IPv4Address` | IPv4 or IPv6 address |
| `URL` | Full URL including scheme |
| `EmailAddress` | Email address |
| `PhoneNumber` | Phone/mobile number |
| `Hash` | File/data hash (MD5, SHA1, SHA256) |

### Personal
| Class | When to use |
|-------|-------------|
| `Person` | A real-world person |
| `Alias` | Username, handle, or alias |
| `Image` | Photo or avatar URL |
| `Document` | A document associated with a person or org |

### Organizations / Affiliations
| Class | When to use |
|-------|-------------|
| `Organization` | Company, NGO, government body |
| `Affiliation` | Membership, relationship between person and org |

### Locations
| Class | When to use |
|-------|-------------|
| `Location` | Physical place (city, country, coordinates) |
| `Country` | Specific country |

### Social Networks
| Class | When to use |
|-------|-------------|
| `FacebookObject` | Facebook profile, page, or post |
| `TwitterUser` | Twitter/X account |
| `InstagramUser` | Instagram account |

### Technology / Devices
| Class | When to use |
|-------|-------------|
| `Website` | A website (use `Domain` for the domain portion) |
| `Port` | Network port |
| `Service` | Network service or software service |
| `Device` | Physical or virtual device |
| `MACAddress` | Hardware MAC address |

### Cryptocurrency
| Class | When to use |
|-------|-------------|
| `BitcoinAddress` | Bitcoin wallet address |
| `CryptoAddress` | Generic cryptocurrency address |

---

## Selection Decision Flow

```
1. Does a standard entity exist for this concept?
   YES → Use it. Import from maltego.entities.
   NO  → Continue to step 2.

2. Is the concept close to a standard entity but needs extra properties?
   YES → Use the standard entity; set extra data via entity.add_property() or subclass if the SDK supports it.
   NO  → Continue to step 3.

3. Is this a genuinely new investigative concept (agents will pivot on it)?
   YES → Define a custom entity. Document: class name, display name, properties, justification.
   NO  → Reconsider. Can you express this as a property on an existing entity instead?
```

---

## Using Standard Entities in Code

```python
from maltego.entities import Domain, IPv4Address, Person, EmailAddress

# Minimal entity (value only)
ip = IPv4Address(value="1.2.3.4")

# Entity with extra properties
person = Person(value="Jane Smith")
person.first_name = "Jane"
person.last_name = "Smith"

# Adding a custom property (when no typed attribute exists)
person.add_property(name="source_system", display_name="Source System", value="example-api")
```

---

## Mapping TRX Entity Strings to SDK Classes

| TRX entity string | SDK class |
|-------------------|----------|
| `maltego.Domain` | `Domain` |
| `maltego.IPv4Address` / `maltego.IPv4Address` | `IPv4Address` |
| `maltego.EmailAddress` | `EmailAddress` |
| `maltego.Person` | `Person` |
| `maltego.Organization` | `Organization` |
| `maltego.URL` | `URL` |
| `maltego.PhoneNumber` | `PhoneNumber` |
| `maltego.Alias` | `Alias` |
| `maltego.Location` | `Location` |
| `maltego.Hash` | `Hash` |
| `maltego.BitcoinAddress` | `BitcoinAddress` |

Unknown strings → flag as custom entity requiring design decision.

---

## When NOT to Create Custom Entities

- The concept maps to an existing class even if the naming differs slightly (e.g., "host" → `Domain`, "IP" → `IPv4Address`).
- The data is metadata about an existing entity, not a new pivot point.
- The concept is only used as an intermediate step and not something an investigator would directly pivot on.

---

## Checking What's Available

To browse available entity classes:

```bash
python -c "import maltego.entities; print(dir(maltego.entities))"
```

Or check the `maltego-transforms-std-entities` package source directly.
