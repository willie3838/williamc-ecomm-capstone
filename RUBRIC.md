# FDE Delivery Readiness Capstone & Grading Rubric

---

# Part 1: FDE Delivery Readiness Capstone Program

**FDE Capstone Project**  
**Shortlink**: `go/fde-capstone-project`

---

## Executive Summary

The FDE Capstone project is the final knowledge confirmation for all new Forward Deployed Engineers (FDEs) and meant as a means to demonstrate you are ‘customer-ready’.

This program is designed to support active learning and help you reach a production-grade standard through professional growth. By inviting you to walk through your architecture and demonstrate working code in a high-stakes simulation, we ensure that every FDE placed in front of a customer is not just a consultant, but a proven builder capable of elevating the quality of our global output.

**Objective:** Validate that you possess the baseline technical rigor (coding, API integration, prompt engineering) and the consultative communication skills required to operate independently.

---

## 1. Project Selection & Sourcing

Supported by your Manager, select a use case from the curated FDE Project Bank (see below). Each project contains a project scope, technical design doc (TDD) and some case studies. These projects are intended as a mock customer scenario and have been compiled to ensure the latest technology is leveraged, the use case is relevant and that the project is at the right depth to be realistic to a real customer scenario. Each project incorporates a subset of mandatory tooling (IAM, terraform, ADK, etc.).

---

## 2. The Build Phase

Once you have selected your project, you should work independently with JetSki/AGY and AI Driven Development best practices to build a functional prototype within your Argolis sandbox. Review the rubric to ensure that your project covers all required components. You should plan for your development to take a maximum of 10 working days and to time bound yourself as you would within a real customer scenario.

For your capstone project, you should:
- Produce a High-Level Architecture Diagram and a working codebase (Ensure permissions are enabled for read access for your panel).
- Prepare a compelling demo for the prototype you built and be prepared to present it in the context of solving the topic from a business, and a technical perspective.
- Develop a presentation on your project in the style of what you would present to the customer at the end of the build. This presentation should:
  - Define the business problem.
  - Introduce the product capabilities / functional requirements.
  - Detail the underlying architecture / non-functional requirements.
  - Be prepared to articulate the cost aspects of the prototype, and be able to articulate the trade-offs gone through during the development process.
  - Discuss the AI Driven Development approach taken.
  - Be approximately 5–8 slides and take ~10 minutes to deliver.

To get started, use your GenAI tools and resources (manager, code repos, fellow FDEs) to seek support as if this was a normal engagement. Per the rubric - you must be able to explain the code and decisions made across your implementation.

---

## 3. The Panel

Once your build is complete, and you have confirmed against the rubric that you are ready, it is time to prepare for your panel review. This collaborative experience is an opportunity for you and 2–3 of your peers to simulate a customer meeting, for you to demo your solution and walk the panelists through your decision matrix, how you built it, and your path to production.

- **For L3, L4, L5 new FDEs**: Your panel should consist of 1 senior FDE and 2 peers.
- **For L6+ new FDEs**: Your panel should include 2 senior FDEs and a peer.
*(The managers do not have to be your direct line manager).*

With the panelists serving as the customer, playing the roles of CTO, CIO, CFO, etc., they will review your project ahead of the panel discussion for production-grade alignment: secure IAM practices, modular code structure, robust error handling, and the ability to explain your implementation choices against edge-case scenarios. You should answer questions, navigate stakeholder concerns, and ultimately present your solution. Your meeting will last approx 1 hour.

Following the panel, the panelists will reconvene without you and together will discuss your project to decide if you are fully ‘customer-ready’ or would benefit from more development. All feedback will be shared directly with you and your line manager to support additional coaching as required. If you need a follow-up session (and don’t worry, we anticipate that many will want/need a second go-round), please aim to schedule another review within two weeks with the same panelists after you take their feedback on board (schedule permitting).

---

## The Topic Bank

- **FDE Onboarding Individual Projects**: [Google Drive Folder](https://drive.google.com/drive/folders/1ON6-L3KKDE69rO4jE2Dghs1P4iT2LIO7?resourcekey=0-XJxYqJ5SAguC_zm97PzjWg&usp=drive_link)
- **Custom Project**: You may also submit a custom project idea to your direct manager for approval rather than choose from the above. It must still adhere to the full rubric and presentation requirements above. FDE must provide a full TDD and Scope similar to the defined projects above.

### Team Central Repositories:
- **GTM FDE**: [github.com/cloud-ai-fde](https://github.com/cloud-ai-fde) (Create a new “Personal Repository”)
- **Delta FDE**: [github.com/delta-fde](https://github.com/delta-fde) (`go/new-delta-fde-repo`)

---

## Conclusion

The FDE Capstone project ensures that we never sacrifice quality for speed. It guarantees that on Day 1 of their "Customer-Ready" status, every FDE has been rigorously calibrated against our highest internal standards, possesses the confidence to handle executive pushback, and has already contributed a reusable, high-value asset to the Google Cloud AI library. Once you have successfully completed your panel, we look forward to you paying forward the favour and sitting on panels for your peers so that together we can shape the future FDE talent!

Please reach out to `ai-tech-gtm-enablement@` with any questions!

---
---

# Part 2: The Grading Rubric

## The Grading Scale

*The following scale will be used to assign a grade to each competency you are demonstrating.*

| Score | Level | Definition |
| :--- | :--- | :--- |
| **0** | **Not Demonstrated** | The Noogler missed the mark, ignored the requirement, or could not answer basic questions. *(Growth Opportunity)* |
| **1** | **Awareness** | The Noogler understands the concept but struggles to apply it practically or misses critical edge cases. *(Needs Additional Coaching)* |
| **2** | **Competent** | The Noogler articulates a solid approach, understands trade-offs, and meets the expectations of a Field-Ready FDE. *(Pass)* |
| **3** | **Proficient** | The Noogler demonstrates deep, production-level expertise, anticipates complex failure modes, and teaches the panel something new. *(Strong Pass)* |

---

## How to Pass & Move Forward

As an FDE, your role bridges between how you build something and how you convey what you have built to our customers. As such, to wrap up the project and be ready for field status, you need to show solid baseline skills in two distinct areas:
- **Section 1: Presentation & Advisory Rigor**
- **Section 2: Engineering & Implementation Excellence**

### Scoring Rules:
1. You will need an **average score of 2-Competent** across each of the 2 sections.
2. Scoring a **0 (Not Demonstrated)** on *any* single metric means you'll need to hit pause, address any specific gaps, and re-present to the panel within two weeks.
3. Following your presentation, your panel will provide detailed feedback including how you score for each component. Your results will also be shared with your manager to support additional coaching as required.

---

## Section 1: Presentation & Advisory Rigor (Part A)

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Strategic Delivery & Value Articulation** | Can they connect technical architecture to business value? Can they clearly articulate why they built this solution and how it handles commercial reality? | Delivers a compelling, narrative-driven walkthrough of the user experience framed around customer personas and operational impact. Explicitly justifies why the architecture directly solves the root business problem (avoiding a "science project") and presents a viable Total Cost of Ownership (TCO) model that demonstrates fiscal responsibility. |
| **2. Objection Handling & Technical Defense** | How do they react to executive pushback, and can they programmatically defend their implementation choices? | Remains entirely calm, collected, and collaborative under pressure when facing stakeholder resistance. Confidently defends engineering decisions and structural design choices during the Q&A matrix using data-backed logic, while cleanly evaluating and addressing technical trade-offs (e.g., cost vs. latency, model tiering). |
| **3. Presentation skills** | How effectively do they manage time, pacing, and the overall flow of the meeting? | Paces the presentation to finish on time. Tactfully steers the panel away from rabbit holes, offering to take tangential topics offline without being dismissive. Demonstrates intellectual honesty by confidently admitting "I don't know, but I will get back to you" rather than fabricating answers. |
| **4. AI Driven Development Discussion** | How effectively do they demonstrate the use of GenAI tools and harness concepts to accelerate their own development lifecycle and code quality? | Articulates how their harness was set up before coding. Demonstrates understanding of establishing key guidance that enables both “in the loop” (quick feature fix that adheres to spec, etc.) and “outside the loop” (goal driven - task is taken and executed in a loop through lint, test, etc. until goal is passed) development. Are mistakes by the agent/harness/etc. incorporated back into agent instructions? |
| **5. Futures / Roadmap** | Can they communicate what the next phase of development would look like while driving home the value of Google Cloud? | Articulates a clear, progressive roadmap for future development phases, addressing key elements like production-grade scalability, performance optimization, etc. but also features of the solution that the customer would likely want or need in production deployment. Effectively demonstrates the strategic value of Google Cloud integration, explaining how native GCP services can be leveraged to enhance stability, security, and long-term business value. |

---

## Section 2: Engineering & Implementation Excellence (Part B)

### 1. AI/ML Engineering

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Agentic & Multi-Agent Systems** | Agent orchestration patterns, tool/function calling, planning and reasoning loops, memory and state management, multi-agent coordination, cognitive architectures, and integrating agents with legacy/external APIs. | **Is at a Competent level on two or more of the following:**<br>• Designs, implements cognitive architectures, orchestration patterns solving business problems, aligning with Critical User Journeys (CUJs).<br>• Builds functional planning, reasoning loops; utilizes session memory, state management ensuring context retention, goal achievement, avoiding execution loops.<br>• Implements tool, function calling integrating agents with legacy, external APIs; respects data boundaries, maintains system security.<br>• Coordinates multi-agent interactions, delivering cohesive user experience, transitioning prototypes into production-ready workflows.<br>• Ensures smooth operation within enterprise thresholds, meeting latency SLAs, maintaining graceful error handling. |
| **2. Retrieval & Data Engineering for AI** | RAG architecture patterns, embedding models and vector databases, chunking and indexing strategies, hybrid search, grounding and citation, data pipelines for AI, parsing complex document formats (PDF/HTML tables), and citation/grounding. | **Is at a Competent level on one or more of the following:**<br>• Implements RAG architecture patterns, embedding models, vector databases.<br>• Executes optimal chunking, indexing strategies; configures hybrid search maximizing retrieval precision.<br>• Ensures reliable grounding, citation mechanisms mitigating hallucinations.<br>• Orchestrates data pipelines parsing complex document formats (PDF/HTML tables).<br>• Validates retrieval quality against business requirements; maintains technical rigor ensuring production-grade data trust. |
| **3. Model Selection, Tuning & Optimization** | Model assessment and selection (quality, latency, cost, context), tuning, quantization, distillation, prompt engineering, structured output enforcement (JSON mode), and inference optimization.<br>Data engineering (preparation, labeling, synthetic generation), architecture selection (encoder/decoder). | **Is at a Competent level on two or more of the following:**<br>• Assesses, selects models balancing quality, latency, cost, context.<br>• Performs tuning, quantization, distillation; optimizes inference.<br>• Refines behavior via prompt engineering; enforces structured JSON outputs.<br>• Manages data engineering: preparation, labeling, synthetic generation.<br>• Selects optimal architectures including encoder/decoder. |
| **4. LLM Ops and Evaluation** | Evaluation methodology for generative AI, quality metrics (faithfulness, relevance, coherence), eval dataset design, human vs. automated evaluation, regression detection, Observability (tracing/logging). | **Is at a Competent level on one or more of the following:**<br>• Applies evaluation methodology; utilizes quality metrics (faithfulness, relevance, coherence, precision, recall, BLEU / ROUGE [if needed], must be more than LLM-as-a-Judge, etc.).<br>• Designs eval datasets; executes human, automated evaluation.<br>• Detects regressions; implements observability via tracing, logging. |
| **5. Domain-Applied AI/ML Expertise** | Translation of vertical-specific business KPIs into AI/ML objectives and architectures. Domain-specific feature engineering, data handling, and regulatory compliance, and privacy regulations (e.g., HIPAA, FINRA). Integration of AI solutions with industry-standard legacy systems and workflows. | **Is at a Competent level on one or more of the following:**<br>• Translates vertical-specific business KPIs into AI/ML objectives, architectures.<br>• Executes domain-specific feature engineering, data handling; ensures regulatory compliance, privacy (e.g., HIPAA, FINRA).<br>• Integrates AI solutions with industry-standard legacy systems, workflows. |

---

### 2. Scoping and Documentation

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Problem Definition** | Identifying and articulating the business problem, translating ambiguity into a technical opportunity, documenting what success unlocks for the customer. | **Is at a Competent level on one or more of the following:**<br>• Identifies, articulates business problems clearly; translates ambiguity into actionable technical opportunity.<br>• Documents customer success unlocks, justifying architecture as direct solution to root business problem while avoiding "science projects".<br>• Anchors scoping decisions to Critical User Journeys (CUJs) and "Definition of Done," bridging technical framework with commercial value. |
| **2. Technical Scope & Constraints** | Defining technical scope, identifying constraints and assumptions, documenting system boundaries and the architectural approach prior to build. | **Is at a Competent level on one or more of the following:**<br>• Defines technical scope precisely; identifies critical constraints and assumptions.<br>• Documents system boundaries and architectural approach prior to build phase.<br>• Ensures technical feasibility by aligning with enterprise infrastructure and security guardrails, while maintaining clear separation between prototype features and production-grade requirements. |
| **3. Stakeholder Alignment & Success Criteria** | Evidence of stakeholder alignment, defined success criteria and acceptance criteria, phased delivery plan or architectural roadmap. | **Is at a Competent level on one or more of the following:**<br>• Demonstrates robust stakeholder alignment; defines clear success and acceptance criteria.<br>• Develops a comprehensive phased delivery plan or architectural roadmap.<br>• Ensures technical milestones synchronize with business expectations, providing a transparent path to production and measurable impact. |
| **4. System Design Artifacts** | Architecture diagrams, data flow diagrams, sequence diagrams. | **Is at a Competent level on one or more of the following:**<br>• Produces comprehensive architecture, data flow, and sequence diagrams clearly mapping system components, interaction patterns, and data lifecycles.<br>• Ensures artifacts accurately reflect technical approach, facilitating peer review and stakeholder alignment on end-to-end system design. |
| **5. Decision Records** | ADRs, documenting trade-offs, alternatives considered, rationale. | **Is at a Competent level on one or more of the following:**<br>• Maintains comprehensive Architecture Decision Records (ADRs) documenting critical trade-offs, alternatives considered, and logical rationale.<br>• Ensures technical transparency and historical context for architectural evolution. |
| **6. API Documentation** | OpenAPI specs, integration guides, SDK documentation. | **Is at a Competent level on one or more of the following:**<br>• Delivers precise OpenAPI specifications, detailed integration guides, and clear SDK documentation.<br>• Facilitates developer adoption and ensures predictable system interactions. |
| **7. Operational Documentation** | Deployment guides, runbooks, onboarding docs, troubleshooting guides. | **Is at a Competent level on one or more of the following:**<br>• Produces actionable deployment guides, runbooks, onboarding documentation, and troubleshooting guides.<br>• Ensures operational continuity and simplifies system management/handoffs. |

---

### 3. Security, Privacy & Compliance

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Authentication & Authorization** | Service accounts, IAM, API key scoping, OAuth/OIDC, Least Privilege. | **Is at a Competent level on two or more of the following:**<br>• Implements robust authentication/authorization via Service Accounts, scoped API keys, and OAuth/OIDC.<br>• Enforces Principle of Least Privilege across all IAM configurations. |
| **2. Infrastructure & Network Security** | VPC design, network segmentation, private endpoints, zero-trust architecture, service perimeters, firewall policies. | **Is at a Competent level on two or more of the following:**<br>• Designs secure VPCs with network segmentation, private endpoints, and zero-trust principles.<br>• Configures service perimeters and firewall policies protecting enterprise assets. |
| **3. Data Protection & Privacy** | Encryption at rest/transit, PII handling, data classification, DLP, Secrets management. | **Is at a Competent level on two or more of the following:**<br>• Ensures encryption at rest/transit; manages PII handling, data classification, and DLP.<br>• Utilizes secure Secrets management preventing credential exposure. |
| **4. AI-Specific Security** | Prompt injection mitigation, output filtering, guardrails, model access controls, content safety. | **Is at a Competent level on two or more of the following:**<br>• Implements prompt-injection mitigation, output filtering, and structural guardrails.<br>• Configures model access controls and content safety layers protecting against adversarial use. |
| **5. Compliance & Governance** | Audit logging, data residency, regulatory requirements, policy enforcement. | **Is at a Competent level on one or more of the following:**<br>• Configures audit logging and data residency aligning with regulatory requirements.<br>• Enforces enterprise policy across all deployments ensuring governance compliance. |

---

### 4. Reliability & Resilience

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Availability Design** | Redundancy, failover, health checks, SLO/SLA definition, distributed systems patterns. | **Is at a Competent level on one or more of the following:**<br>• Implements redundancy, failover, and health checks aligning with SLO/SLA definitions.<br>• Utilizes distributed patterns (consistency, partitioning, multi-region) ensuring high availability. |
| **2. Observability** | Structured logging, metrics, distributed tracing, AI-specific monitoring. | **Is at a Competent level on one or more of the following:**<br>• Configures structured logging, metrics, and distributed tracing.<br>• Monitors AI-specific KPIs (latency, token usage, quality) ensuring runtime visibility and performance tracking. |
| **3. Failure & Recovery Testing** | Failure injection, red teaming, disaster recovery validation, backup/restore testing. | **Is at a Competent level on one or more of the following:**<br>• Executes failure injection, red teaming, and disaster recovery validation.<br>• Performs backup/restore and resilience testing under degraded conditions verifying recovery protocols. |
| **4. Graceful Degradation** | Fallback strategies, circuit breakers, retry policies, timeout handling. | **Is at a Competent level on one or more of the following:**<br>• Implements fallback strategies, circuit breakers, and retry policies.<br>• Configures timeout handling ensuring system stability during partial failures or high load. |

---

### 5. Performance & Cost Optimization

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Scalability & Elasticity** | Horizontal and vertical scaling strategies, autoscaling policies, load balancing. | **Is at a Competent level on one or more of the following:**<br>• Designs horizontal/vertical scaling strategies with autoscaling policies and load balancing.<br>• Optimizes API throughput and HPC/GPU cluster scaling for performant inference. |
| **2. Resource Efficiency** | Compute/GPU right-sizing, autoscaling strategies, spot/preemptible usage. | **Is at a Competent level on one or more of the following:**<br>• Right-sizes compute/GPU resources; utilizes autoscaling and spot/preemptible instances.<br>• Minimizes resource waste while maintaining performance targets. |
| **3. AI Cost Management** | Model selection trade-offs, response caching, batching, memory and embeddings, token optimization. | **Is at a Competent level on one or more of the following:**<br>• Evaluates model selection trade-offs; implements response caching, batching, and embedding optimization.<br>• Manages tokens and context window usage ensuring fiscal responsibility. |

---

### 6. Operational Excellence

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. CI/CD & Deployment** | Pipeline design, deployment strategies, rollback automation. | **Is at a Competent level on one or more of the following:**<br>• Designs automated pipelines with blue/green or canary deployment strategies.<br>• Implements rollback automation ensuring safe, repeatable code releases. |
| **2. Infrastructure as Code** | Terraform/Pulumi, Cloud Build, reproducible environments, environment parity. | **Is at a Competent level on one or more of the following:**<br>• Utilizes Terraform/Pulumi and Cloud Build for reproducible environments.<br>• Ensures strict environment parity between development, staging, and production. |
| **3. AI Lifecycle Management** | Model and agent versioning, A/B testing, configurations, experiment tracking. | **Is at a Competent level on one or more of the following:**<br>• Manages model/agent versioning, A/B testing, and configuration.<br>• Implements experiment tracking and operational tooling for scalable agent management. |
| **4. Testing & Quality Engineering** | Unit, integration, e2e testing, load and performance testing. | **Is at a Competent level on one or more of the following:**<br>• Executes unit, integration, and e2e testing with load/performance validation.<br>• Maximizes test automation and coverage ensuring production-grade reliability. |

---

### 7. Designing for Change

| Competency Area | Assessment Focus | What "2 - Competent" Looks Like (Pass) |
| :--- | :--- | :--- |
| **1. Modularity & Abstraction** | Loose coupling, interface contracts, model swappability, dependency injection. | **Is at a Competent level on one or more of the following:**<br>• Enforces loose coupling and interface contracts facilitating model swappability.<br>• Utilizes dependency injection ensuring modular, maintainable code structures. |
| **2. Configuration Management** | Environment separation, feature flags, externalized config. | **Is at a Competent level on one or more of the following:**<br>• Separates environment configurations using feature flags and externalized settings (i.e. env files, secrets as env, etc.).<br>• Enables dynamic system adjustments without code changes. |
| **3. API Design & Versioning** | Backward compatibility, contract-first design, schema evolution. | Implements contract-first design with backward compatibility. Manages schema evolution ensuring stable integrations across system updates. |
| **4. Extensibility** | Plugin patterns, event-driven architecture, webhook/callback support. | Utilizes plugin patterns and event-driven architectures (webhooks/callbacks). Enables system extensions and integrations with minimal core-logic disruption. |
