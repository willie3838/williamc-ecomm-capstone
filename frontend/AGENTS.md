# Frontend Agent Guide: React & TypeScript UI

Welcome to the frontend application of the **Best Buy Catalog Comparison Agent**. This client interface provides a fast, responsive, and grounded product comparison experience for Best Buy customers.

---

## 1. Technical Stack & Standards

- **Framework**: React 18+ (Vite)
- **Language**: TypeScript (strict mode enabled)
- **Styling**: Tailwind CSS (Best Buy blue `#0046be` and yellow `#fff000` color palette)
- **State Management**: React Query / TanStack Query for server state caching and optimistic updates
- **Component Design**: Atomic design principles with accessible ARIA standards

---

## 2. Directory Layout

```
frontend/
├── AGENTS.md                  # This file (frontend engineering guide)
├── package.json               # Node dependencies and scripts
├── tsconfig.json              # TypeScript compiler configuration
├── vite.config.ts             # Vite build & dev server config
├── tailwind.config.js         # Tailwind styling tokens
└── src/
    ├── main.tsx               # App entrypoint
    ├── App.tsx                # Root layout
    ├── api/                   # Backend client
    │   └── client.ts          # Axios / Fetch client calling /api/compare
    ├── components/
    │   ├── SearchBar.tsx      # Query input with category pills
    │   ├── ComparisonTable.tsx# Side-by-side feature matrix
    │   ├── CitationChip.tsx   # Verified SKU badge linking to BestBuy.com
    │   ├── RecommendationCard.tsx # Agent narrative summary and pros/cons
    │   └── SkeletonLoader.tsx # Shimmer loading animation during generation
    └── types/
        └── comparison.ts      # TypeScript interfaces mirroring backend schemas
```

---

## 3. Key UX Requirements & Guidelines

### 1. Side-by-Side Comparison Matrix
- Render attributes dynamically based on product category (e.g. RAM, Storage, CPU for Laptops; Battery Life, Noise Cancellation for Headphones).
- Highlight winning / superior specifications with subtle badge indicators where unambiguous (e.g., higher battery life).

### 2. Verified SKU Citation Badges
- Every product claim must display an interactive SKU badge (`[SKU: 6534606]`).
- Clicking the badge opens the official product listing on BestBuy.com in a new tab: `https://www.bestbuy.com/site/sku/{sku}.p`.

### 3. Latency & Perceived Performance
- Total backend roundtrip target is $\le 3.0$ seconds.
- Provide immediate visual feedback within 100ms: activate the `SkeletonLoader` immediately upon query submission.
- Display latency indicator or "verified grounded in BigQuery" status chip.

---

## 4. Development Workflow & Commands

```bash
# Install dependencies
npm install

# Run local development server
npm run dev

# Run type checks and linter
npm run lint

# Build production bundle
npm run build
```
