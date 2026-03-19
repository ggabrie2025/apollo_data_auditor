# Test owner_domain sur Windows - Guide Standalone

## Prerequis

Machine Windows (physique ou VM) avec:
- Python 3.10+
- Rust toolchain (rustup)
- Internet pour pip/cargo

## Installation rapide (PowerShell Admin)

```powershell
# 1. Clone ou copier le dossier apollo_io_native
# 2. Ouvrir PowerShell en Admin
cd C:\path\to\apollo_io_native

# 3. Installer maturin
pip install maturin

# 4. Build
maturin build --release

# 5. Installer le wheel
$wheel = Get-ChildItem -Path "target\wheels\*.whl" | Select-Object -First 1
pip install $wheel.FullName --force-reinstall

# 6. Test
python test_owner_domain.py
```

## Resultats attendus

### Machine NON jointe a un domaine AD
```
owner_domain: 0 (hex: 00000000)
```
C'est NORMAL - pas de domaine AD = hash 0.

### Machine jointe a un domaine AD
```
owner_domain: 2847593221 (hex: a9d3f105)
```
Hash xxhash32 du nom de domaine (ex: "CORP.CONTOSO.COM").

## Test minimal inline

```python
import apollo_io_native as aio

# Verifier struct size
assert aio.raw_metadata_size() == 156, "FAIL: size != 156"
print("OK: 156 bytes")

# Test fichier systeme
raw = aio.collect_raw_metadata(r"C:\Windows\System32\drivers\etc\hosts", zone=1)
meta = aio.parse_raw_metadata(raw)
print(f"owner_domain: {meta['owner_domain']:08x}")
print(f"size: {meta['size']}, entropy: {meta['entropy']:.2f}")
```

## Validation completee

| Plateforme | Struct 156B | collect_raw | parse_raw | owner_domain |
|------------|-------------|-------------|-----------|--------------|
| macOS ARM  | OK          | OK          | OK        | 0 (expected) |
| Linux x64  | -           | -           | -         | -            |
| Windows    | -           | -           | -         | Needs test   |

## Commits de reference

- Rust modules: `a75ef6e`
- Main project: `9247264`
