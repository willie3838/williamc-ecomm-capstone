# Frontend Agent Guide: React & TypeScript UI

Welcome to the frontend application of the **TechBuy Retailers Catalog Comparison Agent**. This client interface provides a fast, responsive, and grounded product comparison experience for TechBuy Retailers customers.

---

## 1. Technical Stack & Standards

- **Framework**: React 18+ (Vite)
- **Language**: TypeScript (strict mode enabled)
- **Styling**: Tailwind CSS (TechBuy blue `#0046be` and yellow `#fff000` color palette)
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
    ├── data/                  # Grounded catalog SKU dataset
    │   └── catalogProducts.ts # 40 verified catalog SKUs and category filter helper
    ├── components/
    │   ├── SearchBar.tsx      # Query input with interactive category pills
    │   ├── ComparisonTable.tsx# Side-by-side feature matrix
    │   ├── CitationChip.tsx   # Verified SKU badge linking to modal or canonical TechBuy listing
    │   ├── RecommendationCard.tsx # Agent narrative summary and pros/cons (with Ask Follow-up Questions CTA)
    │   ├── ConversationSidebar.tsx # Interactive follow-up chat sidebar grounded in compared SKUs & matrix
    │   ├── ProductCard.tsx    # Individual product spec card with compare checkbox and View at TechBuy button

    │   ├── ProductDetailsModal.tsx # Accessible in-app modal displaying comprehensive product specifications, stock status, ratings, and grounding
    │   ├── ProductSelectionTray.tsx # Floating selection tray for multiselect comparison
    │   └── SkeletonLoader.tsx # Shimmer loading animation during generation
    └── types/
        └── comparison.ts      # TypeScript interfaces mirroring backend schemas
```

---

## 3. Key UX Requirements & Guidelines

### 1. Side-by-Side Comparison Matrix
- Render attributes dynamically based on product category (e.g. RAM, Storage, CPU for Laptops; Battery Life, Noise Cancellation for Headphones).
- Highlight winning / superior specifications with subtle badge indicators where unambiguous (e.g., higher battery life).

### 2. Verified SKU Citation Badges, Category Browsing, Multiselect & In-App Product Details
- Every product claim must display an interactive SKU badge (`[SKU: 6534606]`).
- Clicking "View at TechBuy" on any `ProductCard` or clicking any `CitationChip` opens the in-app `ProductDetailsModal` displaying full product specifications, description, price, customer reviews & rating, stock status, and BigQuery grounding metadata.
- The `ProductDetailsModal` is accessible, closes via `Escape` key or backdrop click, and allows adding/removing products directly to the compare tray.
- Clicking the **TECHBUY RETAILERS** header logo returns the user to the homepage (All Categories catalog view).
- The catalog browser defaults to showing **All Categories** (all 40 verified catalog SKUs) on initial load and upon returning home. Clicking any category filter pill (`Laptops`, `Tablets`, `Headphones`, `Smart Home`, `TVs`) filters to the relevant category SKUs.
- While browsing catalog categories, users can multiselect products via the `+ Compare` / `Selected` checkbox badge on each `ProductCard`.
- Selecting products immediately displays the floating `ProductSelectionTray` showing selected count, thumbnails, removable chips, clear action (with `Escape` key shortcut support), and a "Compare Selected (N)" button that executes the comparison query across the selected SKUs.
- **Spacious & Auto-Expanding SearchBar (`SearchBar.tsx`)**:
  - The search container features a widened `max-w-5xl` layout with comfortable padding (`p-2 sm:p-2.5`) for entering detailed comparison context.
  - **Dedicated Tagged SKU Chips Row**: When `taggedProducts` are present, tagged SKU chips render in their own dedicated row (`data-testid="tagged-products-row"`) above the text input area. This guarantees the input area maintains full horizontal width regardless of how many SKUs are tagged.
  - **Auto-Expanding Multiline Textarea**: The input uses an auto-expanding `<textarea rows={1}>` (with `role="textbox"` for accessibility) that dynamically expands its height based on `scrollHeight` up to a maximum height of `192px` (`max-h-48` with `overflow-y-auto`), resetting to single-row height upon clear or query reset.
  - **Keyboard Shortcuts**: Pressing `Enter` (without Shift) submits the comparison form (preventing accidental newlines), `Shift+Enter` inserts a newline for multiline prompt drafting, and `Backspace` on an empty input removes the most recently tagged SKU chip.
  - **Interactive SKU Tags Integration**: During multi-select browsing in catalog categories, `selectedProducts` are bound directly as `taggedProducts` to `SearchBar`. Upon comparison completion, if no SKU tags are active, compared products automatically populate as SKU tags. Submitting implicitly constructs a rich, grounded prompt (`buildComparisonPrompt`) encapsulating all tagged SKU attributes alongside user follow-up instructions, supported by backend `ComparisonRequest.query` max_length of 4000.


### 3. Latency & Perceived Performance
- Total backend roundtrip target is $\le 3.0$ seconds.
- Provide immediate visual feedback within 100ms: activate the `SkeletonLoader` immediately upon query submission.
- Display latency indicator or "verified grounded in BigQuery" status chip.

### 4. Interactive Follow-Up Chat Sidebar (`ConversationSidebar.tsx`)
- Clicking "Ask Follow-up Questions" on `RecommendationCard` or the sticky "Chat" toggle button opens the responsive `ConversationSidebar`.
- **Parallel Multi-Pane View**: The comparison summary, product cards, and side-by-side `ComparisonTable` matrix remain fully visible and interactable alongside the sidebar.
- **Strictly Grounded Multi-Turn Thread**: Follow-up questions are submitted to `POST /api/chat` via `sendChatMessage(request)`, grounded strictly in the compared products and matrix rows.
- **Rich Citation Chips & Suggested Follow-ups**: Responses include clickable SKU citation chips (`[SKU: ...]`) that open the in-app `ProductDetailsModal`, as well as clickable suggested follow-up chips that populate the chat prompt.
- **Session Continuity**: Multi-turn history is preserved in client state across queries in the same session.

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
