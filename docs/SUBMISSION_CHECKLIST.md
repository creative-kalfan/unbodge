# Nebius × NVIDIA Global AI Hackathon — Submission Checklist

Use this checklist to complete the Devpost submission for UNBODGE.

---

## Submission Details

| Field | Submission Value / Status | Location in Repo |
| :--- | :--- | :--- |
| **Project Name** | `UNBODGE` | [docs/HACKATHON_SUBMISSION.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_SUBMISSION.md) |
| **Tagline** | `Evidence-gated autonomous software maintenance agent that removes obsolete workarounds through historical counterfactual execution.` | [docs/HACKATHON_SUBMISSION.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_SUBMISSION.md) |
| **Track** | `Coding and Agentic Engineering` | [docs/HACKATHON_SUBMISSION.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_SUBMISSION.md) |
| **Description** | Complete markdown description covering Problem, Solution, Architecture, and Invariants. | [docs/HACKATHON_SUBMISSION.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_SUBMISSION.md) |
| **Public Repository URL** | `https://github.com/creative-kalfan/unbodge` *(verify public visibility)* | [README.md](file:///c:/Users/pathan%20Kalfan/unbodge/README.md) |
| **Open Source License** | `MIT License` | [LICENSE](file:///c:/Users/pathan%20Kalfan/unbodge/LICENSE) |
| **README** | Updated root README with setup, architecture, test instructions, and limitations. | [README.md](file:///c:/Users/pathan%20Kalfan/unbodge/README.md) |
| **Demo URL** | **TODO (Operator Action):** Host demo or provide reproducible local dashboard instructions (`python scripts/dashboard_demo.py --serve`). | [docs/FINAL_ARCHITECTURE.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/FINAL_ARCHITECTURE.md) |
| **Public YouTube Video URL** | **TODO (Operator Action):** Record demo video using script and upload unlisted/public video to YouTube. | [docs/DEMO_VIDEO_SCRIPT.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/DEMO_VIDEO_SCRIPT.md) |
| **Technology Stack** | Python 3.11+, FastAPI, React 19, TypeScript, Vite, Tailwind CSS v4, Docker, Pydantic v2, Git Plumbing, Redis, PostgreSQL. | [docs/FINAL_ARCHITECTURE.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/FINAL_ARCHITECTURE.md) |
| **Nebius Token Factory Usage** | Documented usage of Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1`) for serverless model inference. | [docs/NEBIUS_NVIDIA_FEEDBACK.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/NEBIUS_NVIDIA_FEEDBACK.md) |
| **NVIDIA Model Usage** | `nvidia/Nemotron-3-Ultra-550b-a55b` used for advisory causal hypothesis reasoning. | [docs/NEBIUS_NVIDIA_FEEDBACK.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/NEBIUS_NVIDIA_FEEDBACK.md) |
| **Technology Feedback** | Comprehensive, candid feedback on Token Factory onboarding, Nemotron behavior, and DX. | [docs/NEBIUS_NVIDIA_FEEDBACK.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/NEBIUS_NVIDIA_FEEDBACK.md) |
| **Development Disclosure** | Clear attribution of prior commit baseline (`27352f5`) vs hackathon-period advancements. | [docs/HACKATHON_DEVELOPMENT_DISCLOSURE.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_DEVELOPMENT_DISCLOSURE.md) |
| **Testing Instructions** | Exact CLI commands to run unit, integration, Docker, and frontend test suites. | [README.md](file:///c:/Users/pathan%20Kalfan/unbodge/README.md) |

---

## Remaining Operator Actions Before Final Submission

1. **Record Video**:
   * Follow [docs/DEMO_VIDEO_SCRIPT.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/DEMO_VIDEO_SCRIPT.md).
   * Ensure screen recording shows:
     * `python scripts/dashboard_demo.py` in terminal.
     * React dashboard running at `http://localhost:5173`.
     * Proof Explorer displaying 4-cell matrix and receipts.
     * Both positive (`PROPOSE_REMOVAL`) and negative (`ABSTAIN`) scenarios.
   * Upload to YouTube and paste link into Devpost.
2. **Review Public Repository**:
   * Confirm GitHub repository is public and `.env` is NOT checked in (`git status`).
3. **Submit Devpost Entry**:
   * Paste content from [docs/HACKATHON_SUBMISSION.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_SUBMISSION.md).
   * Submit before deadline.
