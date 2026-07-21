# Auto Cost Engine — Acceptance Report

> **Project:** AI-Powered Automatic Quantity Calculation & Cost Estimation Engine
> **Client:** Jasfo Design (Interior Fit-Out)
> **Version:** v1.0.0
> **Date:** $(date +%Y-%m-%d)

---

## 1. Module Coverage

| Module | Status | Notes |
|--------|--------|-------|
| **Module 1: Drawing Intelligence** | ☐ | DXF/PDF → detected objects |
| **Module 2: Quantity Engine** | ☐ | Rules → expanded line items |
| **Module 3: Material Selection** | ☐ | BOQ items → material options → selection |
| **Module 4: Cost Engine** | ☐ | Rate → CostBreakdown → CostVersion |
| **Module 5: Client Visualization** | ☐ | 2D viewer, 3D viewer, live updates |

## 2. Dataset Verification

| Dataset | Records | Verified |
|---------|---------|----------|
| Drawing object types | 15+ | ☐ |
| BOQ rules | 20+ | ☐ |
| Wastage rules | 10+ | ☐ |
| Material catalog | 50+ | ☐ |
| Vendor master | 10+ | ☐ |
| Labour rates | 8+ trades | ☐ |
| Productivity rates | 8+ trades | ☐ |
| Company standards | 5+ | ☐ |
| Rate history | logged per change | ☐ |

## 3. AI Feature Verification

| Feature | Works Offline | Uses API Key |
|---------|:------------:|:------------:|
| MiMo v2.5 vision (DWG/PDF) | ☐ (mock) | ☐ |
| DeepSeek V4 Flash Q&A | ☐ (mock) | ☐ |
| Missing BOQ detection | ☐ (mock) | ☐ |
| Anomaly detection | ☐ (mock) | ☐ |
| Value engineering | ☐ (mock) | ☐ |
| Duration prediction | ☐ | N/A |

## 4. End-to-End Journey (Playwright)

| Step | Status | Screenshot |
|------|--------|------------|
| 1. Login via Keycloak | ☐ | `screenshots/01-login.png` |
| 2. Upload DXF drawing | ☐ | `screenshots/02-upload.png` |
| 3. View detected objects (2D) | ☐ | `screenshots/03-2d-viewer.png` |
| 4. Compute quantities | ☐ | `screenshots/04-boq-table.png` |
| 5. View 3D scene | ☐ | `screenshots/05-3d-viewer.png` |
| 6. Select material | ☐ | `screenshots/06-material-select.png` |
| 7. Verify live cost update | ☐ | `screenshots/07-cost-update.png` |
| 8. Ask AI question | ☐ | `screenshots/08-ai-chat.png` |
| 9. Check anomalies | ☐ | `screenshots/09-anomalies.png` |
| 10. Generate proposal PDF | ☐ | `screenshots/10-proposal.png` |

## 5. Performance

| Metric | Target | Actual |
|--------|--------|--------|
| BOQ load (P95) | <2s | — |
| Material select → cost update | <500ms | — |
| compute-quantities (50 concurrent) | <30s | — |
| AI Q&A response (mock) | <3s | — |

## 6. Production Readiness

| Item | Status |
|------|--------|
| docker-compose.prod.yml | ☐ |
| Caddy TLS (Let's Encrypt) | ☐ |
| Health check endpoint | ☐ |
| DB backup script | ☐ |
| DB restore script | ☐ |
| Deploy runbook | ☐ |
| Firewall rules documented | ☐ |
| Resource limits configured | ☐ |

## 7. Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | — | — | — |
| QA | — | — | — |
| Client (Jasfo) | — | — | — |

---

**Total tests:** 166+ (backend) + 0 (frontend)
**Coverage target:** >80% on rule/cost engines
**AI models:** MiMo v2.5 (vision) + DeepSeek V4 Flash (text)
**Stack:** FastAPI · React · PostgreSQL 16 + pgvector · MinIO · Redis · Keycloak · Caddy
