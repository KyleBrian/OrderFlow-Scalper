# Order Flow Scalper - Documentation Index

**Complete guide to all documentation files and what each contains.**

---

## 📚 DOCUMENTATION FILES CREATED FOR YOU

### 1. **ARCHITECTURE_MAP.md** ← START HERE
**Purpose**: Understanding the system structure and how everything fits together  
**Contains**:
- Complete project file structure with descriptions
- Execution flow & threading diagram
- Data flow diagram from MT5 to journal
- Object hierarchy with all attributes
- Key import dependencies
- Configuration hierarchy
- Module inter-dependencies
- Signal confirmation logic
- Threading & synchronization notes
- Common patterns & conventions
- Quick reference tables

**When to read**: You need to understand how modules talk to each other

---

### 2. **INSTALLATION_GUIDE.md** ← FOLLOW THIS STEP-BY-STEP
**Purpose**: Complete setup from scratch to running live trades  
**Contains**:
- System requirements checklist
- Python installation (Windows/Mac/Linux)
- Virtual environment setup
- Dependency installation with verification
- MetaTrader 5 setup (connection, DOM, credentials)
- Configuration walkthrough (`config.py` editing)
- Verification steps (connectivity test, import test)
- Running the system (dry run, then live)
- Comprehensive troubleshooting guide
- Advanced configuration options (killzones, risk levels, thresholds)
- Performance monitoring
- Backup & recovery

**When to read**: You're setting up the system for the first time, or debugging setup issues

---

### 3. **IMPORT_REFERENCE.md** ← USE THIS FOR CODING
**Purpose**: Complete lookup for all imports, classes, and functions  
**Contains**:
- External dependencies table (pip install packages)
- Python standard library modules used
- All internal project imports with examples
- Every module's classes and functions (detailed)
- Module dependency graph (visual)
- Most-used classes & functions table
- Import troubleshooting solutions
- Quick import cheat sheet

**When to read**: You're writing code and need to know what to import, or you're debugging import errors

---

### 4. **README.md** ← PROJECT OVERVIEW
**Purpose**: High-level feature description and architecture intro  
**Contains**:
- Project description (3-thread order flow scalper)
- High-level architecture diagram
- Core components overview
- Installation summary (condensed)
- Usage (condensed)
- Results & output examples
- Project structure tree

**When to read**: You're new to the project and want a quick overview

---

### 5. **QUICK_START.md** ← FASTEST PATH TO RUNNING
**Purpose**: Minimal steps to get trading in 30 minutes  
**Contains**:
- Prerequisites checklist
- 5-minute setup (if already have Python)
- Configuration template (copy-paste values)
- First run verification
- Troubleshooting (most common issues)
- Next steps

**When to read**: You want to get up and running as fast as possible

---

### 6. **CHANGELOG.md**
**Purpose**: Version history and feature additions  
**Contains**:
- All versions with dates
- Features added/changed/removed per version
- Bug fixes
- Breaking changes
- Migration guides

**When to read**: You're upgrading from an old version or want to see what's new

---

### 7. **NEW_FEATURES_GUIDE.md**
**Purpose**: Deep dive into advanced v3+ features  
**Contains**:
- Candle Imbalance Detection (CRT)
- ICT Order Blocks
- Liquidity Delta Profiler (LDP)
- Session Configuration Manager
- Loss Prevention Validator
- Trade Reasoner
- Integration with signal detection

**When to read**: You want to understand or configure the advanced features

---

### 8. **IMPLEMENTATION_SUMMARY.md**
**Purpose**: What was built in this version  
**Contains**:
- Feature summary
- Component descriptions
- Signal detection pipeline
- Risk management rules
- Advanced modules

**When to read**: You want implementation details of specific features

---

## 📖 HOW TO USE THIS DOCUMENTATION

### Scenario 1: "I'm brand new to this project"
1. Read **README.md** (5 min) — understand what it does
2. Read **QUICK_START.md** (10 min) — get the gist
3. Follow **INSTALLATION_GUIDE.md** (30 min) — actually set it up
4. Run **test_connection.py** (5 min) — verify it works
5. Run **dry run** (at least 1 trading session) — see it in action

### Scenario 2: "I have a specific error or problem"
1. Check **INSTALLATION_GUIDE.md → Troubleshooting** section
2. If that doesn't help, check **IMPORT_REFERENCE.md → Import Troubleshooting**
3. Check the log file: `order_flow_scalper.log`
4. Check trade journal for clues: `trade_journal.csv`

### Scenario 3: "I want to understand how it works"
1. Read **ARCHITECTURE_MAP.md** (30 min) — understand structure
2. Read **IMPORT_REFERENCE.md** (15 min) — know what each module does
3. Open the code and trace through with the diagrams

### Scenario 4: "I want to modify/configure the system"
1. Go to **INSTALLATION_GUIDE.md → Advanced Configuration**
2. Reference **IMPORT_REFERENCE.md** for what each parameter controls
3. Check **ARCHITECTURE_MAP.md → Configuration Hierarchy** for defaults
4. Test changes in **DRY_RUN = True** mode first

### Scenario 5: "I want to extend with custom code"
1. Read **ARCHITECTURE_MAP.md → Module Inter-Dependencies**
2. Read **IMPORT_REFERENCE.md** for all available classes/functions
3. Create new module following existing patterns
4. Test thoroughly in dry run mode

---

## 🎯 QUICK LOOKUP TABLE

| Question | Document | Section |
|----------|----------|---------|
| How do I install this? | INSTALLATION_GUIDE | Step 1-6 |
| What does this module do? | ARCHITECTURE_MAP | Module Overview (section 1) |
| How do I import X? | IMPORT_REFERENCE | All modules section |
| What's in config.py? | INSTALLATION_GUIDE + ARCHITECTURE_MAP | Configuration section |
| Why is MT5 connection failing? | INSTALLATION_GUIDE | Troubleshooting |
| How does threading work? | ARCHITECTURE_MAP | Section 2 (Execution Flow) |
| What are the signal confirmations? | ARCHITECTURE_MAP | Section 8 |
| How do I configure risk parameters? | INSTALLATION_GUIDE | Advanced Configuration |
| What are the new features? | NEW_FEATURES_GUIDE | All sections |
| How do I run this? | QUICK_START or INSTALLATION_GUIDE | Step 6 (Running) |
| What's the data flow? | ARCHITECTURE_MAP | Section 3 |

---

## 📊 FILE RELATIONSHIPS

```
README.md (Overview)
    ↓
QUICK_START.md (Fast path)
    ↓
INSTALLATION_GUIDE.md (Detailed setup) ← MOST CRITICAL
    ├─→ ARCHITECTURE_MAP.md (Understanding)
    ├─→ IMPORT_REFERENCE.md (For coding)
    └─→ TROUBLESHOOTING (In guide)
    
When running:
    ├─→ Check ARCHITECTURE_MAP for flow/threading
    ├─→ Check IMPORT_REFERENCE for classes/functions
    └─→ Check log file (order_flow_scalper.log)
    
When modifying:
    ├─→ ARCHITECTURE_MAP (understand impact)
    ├─→ IMPORT_REFERENCE (what to import)
    └─→ INSTALLATION_GUIDE → Advanced Config (parameters)
    
Advanced features:
    └─→ NEW_FEATURES_GUIDE.md

Version info:
    └─→ CHANGELOG.md

Implementation details:
    └─→ IMPLEMENTATION_SUMMARY.md
```

---

## ✅ DOCUMENTATION CHECKLIST

These docs cover:

- ✅ Complete architecture & module structure
- ✅ All imports and dependencies (external & internal)
- ✅ Every class and its attributes
- ✅ Every function/method and its signature
- ✅ Complete installation procedure (all OS)
- ✅ Configuration guide (all parameters)
- ✅ Troubleshooting (common issues + solutions)
- ✅ Threading & synchronization
- ✅ Data flow from MT5 to journal
- ✅ Signal detection pipeline
- ✅ Risk management rules
- ✅ Advanced features (v3+)
- ✅ Quick reference tables
- ✅ Dependency graphs

---

## 🚀 NEXT STEPS

1. **If you haven't installed yet**: Follow **INSTALLATION_GUIDE.md**
2. **If you're debugging an issue**: Check **INSTALLATION_GUIDE.md → Troubleshooting**
3. **If you want to understand the code**: Read **ARCHITECTURE_MAP.md** then **IMPORT_REFERENCE.md**
4. **If you want to modify config**: Read **INSTALLATION_GUIDE.md → Advanced Configuration**
5. **If you're adding features**: Read **ARCHITECTURE_MAP.md** and **IMPORT_REFERENCE.md**

---

## 📝 NOTES

- All documents are in **Markdown (.md)** format
- All code examples are **executable** and **tested**
- All configurations are **clearly labeled** and **easy to find**
- **Cross-references** link between documents
- **Tables and diagrams** make complex concepts visual
- **Troubleshooting sections** cover the most common issues

---

## 💡 TIPS

1. **Save these docs locally** for offline reference
2. **Use Ctrl+F (Find)** to search within documents
3. **Print ARCHITECTURE_MAP.md** for visual reference while coding
4. **Keep INSTALLATION_GUIDE handy** during setup
5. **Bookmark IMPORT_REFERENCE.md** when coding
6. **Check logs frequently** during debugging

---

**You now have complete, comprehensive documentation!**

Start with **INSTALLATION_GUIDE.md** and follow the steps. Good luck! 🎯

---

*Created for OrderFlow-Scalper v3+ (Strategy 1 with Advanced Features)*  
*Updated: July 2026*
