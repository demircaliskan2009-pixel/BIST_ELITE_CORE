# Security Policy

## Supported Versions
We support the latest `main` branch and the latest tagged release (currently `v0.x`).  
Older tags may receive fixes case-by-case.

## Reporting a Vulnerability
Please report security vulnerabilities **privately** via GitHub’s “Report a vulnerability”
(Security → Advisories → *Report a vulnerability*) or by email:
**[replace-with-your-email]**.

- Do **not** open a public issue for security problems.
- Include a minimal PoC, affected version/commit SHA, and impact assessment if possible.

## Our Process & SLAs
- Triage & first response: **48 hours**  
- Status update: every **7 days** until resolution  
- Fix window (severity-based):
  - Critical/High: **7–14 days**
  - Medium: **30 days**
  - Low: best effort

We prefer coordinated disclosure. We will credit reporters in the release notes if they wish.

## Scope (in-scope examples)
- Code execution, privilege escalation, authN/authZ bypass
- Secret leakage, supply-chain risks (Actions/workflows), CI/CD tampering
- Integrity issues in data pipelines that can lead to incorrect trading outputs

## Out of Scope (examples)
- DoS via rate limits, UI/UX kozmetik sorunlar, bilinen bağımlılık uyarıları (Dependabot tarafından zaten kapsanır),
- Sosyal mühendislik, 3. taraf hizmet/altyapı kusurları, varsayılan konfigürasyonla uyumsuz kurulumlar.

## Safe Harbor
İyi niyetli testleriniz için, makul sınırlar içinde ve veriye/hesaplara zarar vermeden hareket ettiğiniz sürece
hukuki işlem başlatmayız. Lütfen yerel yasalarınıza uyun ve üretim dışı ortamlarda test etmeye özen gösterin.
