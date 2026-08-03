/**
 * Tour registry — tours are data, not components.
 *
 * Two kinds:
 *  - "page" tours belong to one route and explain that page. They launch from
 *    the grey tour icon in the page header.
 *  - "walkthrough" tours cross pages in a curated order, one per role. They
 *    launch from the welcome band, the sidebar's "Take the tour", or the
 *    dashboard tour icon.
 *
 * Steps anchor to real elements by CSS selector. Prefer [data-tour-id="…"]
 * attributes added sparingly in page files; stable aria attributes and nav
 * hrefs are fine too. A step whose anchor never becomes visible is skipped,
 * so conditional sections (empty states, streamed data) are safe to target.
 *
 * Copy rules: plain sentences, sentence case, no em dashes, no hype.
 */

export type TourStep = {
  /** CSS selector for the element to spotlight. First visible match wins. */
  anchor: string;
  title: string;
  body: string;
  /** Preferred card side. The overlay flips or clamps when it does not fit. */
  placement?: "top" | "bottom" | "left" | "right";
  /** Walkthroughs only: the route this step lives on. */
  route?: string;
};

export type Tour = {
  id: string;
  kind: "page" | "walkthrough";
  /** Page tours: the exact pathname the tour belongs to. */
  route?: string;
  /** Walkthroughs: the role that owns it. */
  role?: string;
  label: string;
  steps: TourStep[];
};

// ---------------------------------------------------------------------------
// Applicant page tours
// ---------------------------------------------------------------------------

const APPLICANT_PAGE_TOURS: Tour[] = [
  {
    id: "page-applicant-dashboard",
    kind: "page",
    route: "/applicant",
    label: "Dashboard",
    steps: [
      {
        anchor: 'a[href="/applicant/matches"]',
        title: "Your matches",
        body: "Jobs ranked against your profile. Each one shows a score and the reasons behind it.",
        placement: "right",
      },
      {
        anchor: '[data-tour-id="dashboard-best-matches"]',
        title: "Your best matches",
        body: "The strongest fits right now. Open one to see the full breakdown before you apply.",
        placement: "bottom",
      },
      {
        anchor: 'a[href="/applicant/applications"]',
        title: "Applications",
        body: "Every job you have sent, with status and interview requests in one place.",
        placement: "right",
      },
      {
        anchor: 'a[href="/applicant/credentials"]',
        title: "Credentials",
        body: "Add your OSHA, CDL, or NCCER card. We verify it so employers see proof instead of a claim.",
        placement: "right",
      },
      {
        anchor: '[aria-label^="Notifications"]',
        title: "Notifications",
        body: "We ping you when something needs a decision: a new match, a message, or an interview time.",
        placement: "bottom",
      },
    ],
  },
  {
    id: "page-applicant-matches",
    kind: "page",
    route: "/applicant/matches",
    label: "Matches",
    steps: [
      {
        anchor: '[data-tour-id="matches-summary"]',
        title: "How your list reads",
        body: "How many jobs you can apply to today and how many are close. The counts update as your profile improves.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="matches-ready"]',
        title: "Ready to apply",
        body: "You meet every requirement for these jobs. Start here.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="matches-close"]',
        title: "Close matches",
        body: "One or two gaps away. Each card names the gap so you know what to fix.",
        placement: "top",
      },
    ],
  },
  {
    id: "page-applicant-jobs",
    kind: "page",
    route: "/applicant/jobs",
    label: "Browse jobs",
    steps: [
      {
        anchor: 'input[placeholder="Search by title or description..."]',
        title: "Search everything",
        body: "Every job on the platform, not just your matches. Results narrow as you type.",
        placement: "bottom",
      },
      {
        anchor: 'select[aria-label="trade"]',
        title: "Filter the list",
        body: "Cut to your trade, employer, state, or work setting. The list and the map update together.",
        placement: "bottom",
      },
      {
        anchor: '[role="group"][aria-label="Distance radius"]',
        title: "Set your radius",
        body: "Jobs filter to a drive distance from your city. Widen it to see more.",
        placement: "bottom",
      },
    ],
  },
  {
    id: "page-applicant-applications",
    kind: "page",
    route: "/applicant/applications",
    label: "Applications",
    steps: [
      {
        anchor: '[data-tour-id="applications-list"]',
        title: "Everything you have sent",
        body: "Each row shows where the application stands and what happens next. Hired gets its own section.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="applications-calendar"]',
        title: "Interviews on your calendar",
        body: "Confirmed interviews can sync to Google, Outlook, or Apple Calendar. Subscribe once and they stay current.",
        placement: "top",
      },
      {
        anchor: 'a[href="/applicant/matches"]',
        title: "Find the next one",
        body: "Your ranked matches are the fastest route to the next application.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-applicant-credentials",
    kind: "page",
    route: "/applicant/credentials",
    label: "Credentials",
    steps: [
      {
        anchor: '[data-tour-id="credentials-add"]',
        title: "Add a credential",
        body: "Type the name, like OSHA 10 or CDL A. We match it to the standard registry as you type.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="credentials-summary"]',
        title: "Where you stand",
        body: "Total, verified, and in review. Verified credentials carry the most weight with employers.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="credentials-list"]',
        title: "Your record",
        body: "Each row shows its verification status. Verification runs against real registries, not your word.",
        placement: "top",
      },
      {
        anchor: 'a[href="/applicant/consent"]',
        title: "You control sharing",
        body: "Data sharing settings decide which employers can see your verified record.",
        placement: "bottom",
      },
    ],
  },
  {
    id: "page-applicant-chat",
    kind: "page",
    route: "/applicant/chat",
    label: "Planning chat",
    steps: [
      {
        anchor: '[data-tour-id="chat-new"]',
        title: "Start a session",
        body: "Pick a job and the chat opens focused on it: what to fix, what to say, how to get there.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="chat-sessions"]',
        title: "Your sessions",
        body: "Conversations stay here so you can pick up where you left off.",
        placement: "top",
      },
      {
        anchor: 'a[href="/applicant/chat"]',
        title: "Always one click away",
        body: "The planner lives in the sidebar under Plan. Bring a job question any time.",
        placement: "right",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Employer page tours
// ---------------------------------------------------------------------------

const EMPLOYER_PAGE_TOURS: Tour[] = [
  {
    id: "page-employer-dashboard",
    kind: "page",
    route: "/employer",
    label: "Employer dashboard",
    steps: [
      {
        anchor: '[data-tour-id="employer-today"]',
        title: "Today",
        body: "New applications and careers-page sync health in one list. If something needs you, it is here.",
        placement: "bottom",
      },
      {
        anchor: 'a[href="/employer/jobs/add"]',
        title: "Post jobs",
        body: "Write one job or import a batch from your careers page or a spreadsheet.",
        placement: "right",
      },
      {
        anchor: 'a[href="/employer/applications"]',
        title: "Applications",
        body: "Everyone who applied, grouped by job. Review, shortlist, and set interview times.",
        placement: "right",
      },
      {
        anchor: 'a[href="/employer/verified-workers"]',
        title: "Verified workers",
        body: "Search workers with registry-verified credentials who agreed to be visible to employers.",
        placement: "right",
      },
      {
        anchor: 'a[href="/employer/analytics"]',
        title: "Analytics",
        body: "Your pipeline, what to do next, and how your jobs are performing.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-employer-post-jobs",
    kind: "page",
    route: "/employer/jobs/add",
    label: "Post jobs",
    steps: [
      {
        anchor: '[data-tour-id="post-single"]',
        title: "Write one job",
        body: "Best for a specific role. It publishes as soon as you finish writing it.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="post-import"]',
        title: "Import a batch",
        body: "Point us at a careers URL, a CSV, or a pasted list. You review every row before it goes live.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="post-how"]',
        title: "One destination",
        body: "Both routes end in your jobs list and the matching engine. Imports get a quick admin review first.",
        placement: "top",
      },
    ],
  },
  {
    id: "page-employer-jobs",
    kind: "page",
    route: "/employer/jobs",
    label: "Your jobs",
    steps: [
      {
        anchor: '[data-tour-id="jobs-filters"]',
        title: "Filter your postings",
        body: "Search by title, trade, state, or city. Sorting covers posted date and pay.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="jobs-list"]',
        title: "Candidates per job",
        body: "Each job shows its matched and applied counts. Open a job to see its ranked candidates.",
        placement: "top",
      },
      {
        anchor: 'a[href="/employer/jobs/new"]',
        title: "Add another",
        body: "New job posts publish immediately and start matching right away.",
        placement: "bottom",
      },
    ],
  },
  {
    id: "page-employer-applications",
    kind: "page",
    route: "/employer/applications",
    label: "Applications",
    steps: [
      {
        anchor: '[data-tour-id="apps-buckets"]',
        title: "The pipeline at a glance",
        body: "New, in review, interview, decided. Click a bucket to filter the list below.",
        placement: "bottom",
      },
      {
        anchor: 'input[placeholder="Search applicant or job…"]',
        title: "Find a person fast",
        body: "Search by applicant name or job title.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="apps-groups"]',
        title: "Grouped by job",
        body: "Each job expands to its applicants. Act on a row without leaving the page.",
        placement: "top",
      },
    ],
  },
  {
    id: "page-employer-verified-workers",
    kind: "page",
    route: "/employer/verified-workers",
    label: "Verified workers",
    steps: [
      {
        anchor: '[data-tour-id="workers-filters"]',
        title: "Narrow the pool",
        body: "Filter by keyword, trade, state, credentials, and availability. Filters live in the URL so you can share a view.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="workers-results"]',
        title: "Verified and consented",
        body: "Everyone here holds verified credentials and chose to be visible. Reach out from the profile.",
        placement: "top",
      },
      {
        anchor: 'a[href="/employer/messages"]',
        title: "Follow up",
        body: "When a worker replies, the conversation lives in Messages.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-employer-analytics",
    kind: "page",
    route: "/employer/analytics",
    label: "Analytics",
    steps: [
      {
        anchor: '[data-tour-id="analytics-next"]',
        title: "What to do next",
        body: "The candidates and applications waiting on you, before any counting.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="analytics-pipeline"]',
        title: "Pipeline truth",
        body: "These tiles count the same rows as your applications inbox. One number, one meaning.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="analytics-ask"]',
        title: "Ask about your numbers",
        body: "Ask a plain question about your hiring data and get an answer computed from it.",
        placement: "top",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Admin page tours
// ---------------------------------------------------------------------------

const ADMIN_PAGE_TOURS: Tour[] = [
  {
    id: "page-admin-dashboard",
    kind: "page",
    route: "/admin",
    label: "Command center",
    steps: [
      {
        anchor: '[data-tour-id="admin-priority"]',
        title: "Needs your attention",
        body: "Imports, review items, and credentials waiting on a human. Work top to bottom.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="admin-glance"]',
        title: "At a glance",
        body: "Workers, jobs, employers, matches, placements. Each number links to its page.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="admin-funnel"]',
        title: "The funnel",
        body: "Where workers drop off between signup and placement. The takeaway names the worst stage.",
        placement: "top",
      },
      {
        anchor: '[data-tour-id="admin-refresh"]',
        title: "Fresh numbers",
        body: "Refresh re-reads the data. Recompute rescores every applicant against every job.",
        placement: "bottom",
      },
    ],
  },
  {
    id: "page-admin-review",
    kind: "page",
    route: "/admin/review",
    label: "Review",
    steps: [
      {
        anchor: '[role="tablist"][aria-label="Item types"]',
        title: "One queue, typed",
        body: "Guardrail trips, ambiguous credentials, broken links. Filter by type or work the full list.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="review-feed"]',
        title: "Decide and move on",
        body: "Each item carries the context you need to approve, reject, or fix.",
        placement: "top",
      },
      {
        anchor: 'a[href="/admin/audit"]',
        title: "Every decision is logged",
        body: "Admin actions write to the audit log automatically.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-admin-imports",
    kind: "page",
    route: "/admin/job-imports",
    label: "Job imports",
    steps: [
      {
        anchor: '[role="tablist"][aria-label="Batch filters"]',
        title: "The queue",
        body: "Awaiting batches come first. Approving publishes staged rows to the live board.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="imports-list"]',
        title: "Batches and pulls",
        body: "Employer submissions and careers-page pulls share one queue. Open a batch to review rows.",
        placement: "top",
      },
      {
        anchor: 'a[href="/admin/career-sources"]',
        title: "Source health",
        body: "Career sources tracks every connected page and its sync history.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-admin-credentials",
    kind: "page",
    route: "/admin/credentials",
    label: "Credentials",
    steps: [
      {
        anchor: "#queue",
        title: "The daily queue",
        body: "Workers type credential names free-form. Confirm the uncertain registry matches here.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="credentials-ingest"]',
        title: "Bulk ingestion",
        body: "Partner institutions can send credentials by CSV or SIS. It stays collapsed until you need it.",
        placement: "top",
      },
      {
        anchor: 'a[href="/admin/review"]',
        title: "Escalations",
        body: "Credentials the verifier could not settle appear in Review with the other flagged items.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-admin-matching",
    kind: "page",
    route: "/admin/matching",
    label: "Matching",
    steps: [
      {
        anchor: '[data-tour-id="matching-weights"]',
        title: "Dimension weights",
        body: "How much each of the nine dimensions counts. The sum must stay at 100.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="matching-gates"]',
        title: "Hard gates",
        body: "A failed gate caps the score. It never hides inside a blended number.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="matching-preview"]',
        title: "Preview, then activate",
        body: "See how the marketplace shifts before you commit. Activation is versioned, audited, and rescores everyone.",
        placement: "top",
      },
    ],
  },
  {
    id: "page-admin-career-sources",
    kind: "page",
    route: "/admin/career-sources",
    label: "Career sources",
    steps: [
      {
        anchor: "main h1",
        title: "How syncing works",
        body: "First pulls learn a site's structure. After that, re-syncs are incremental and quick.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="sources-list"]',
        title: "Connected pages",
        body: "Every careers page we pull from, with sync health per source. Expand one for its full activity log.",
        placement: "bottom",
      },
      {
        anchor: 'a[href="/admin/job-imports"]',
        title: "Where pulls land",
        body: "New rows from these sources arrive in the imports queue for review.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-admin-applicants",
    kind: "page",
    route: "/admin/applicants",
    label: "Applicants",
    steps: [
      {
        anchor: '[data-tour-id="applicants-filters"]',
        title: "Find anyone",
        body: "Search by name, email, state, or job family. Results update as you type.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="applicants-table"]',
        title: "The directory",
        body: "Every worker on the platform. Open a row for the full profile and match history.",
        placement: "top",
      },
      {
        anchor: 'a[href="/admin/view-as"]',
        title: "See what they see",
        body: "View as applicant renders the product exactly as a chosen worker sees it, read-only.",
        placement: "right",
      },
    ],
  },
  {
    id: "page-admin-map",
    kind: "page",
    route: "/admin/map",
    label: "Map",
    steps: [
      {
        anchor: 'select[aria-label="Filter by trade family"]',
        title: "Cut by trade",
        body: "The map redraws for one trade so you can see its supply and demand alone.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="map-canvas"]',
        title: "Jobs on the ground",
        body: "Clusters break apart as you zoom. Click a pin for the jobs at that site.",
        placement: "right",
      },
      {
        anchor: '[data-tour-id="map-panel"]',
        title: "The numbers beside the map",
        body: "Supply and demand for what the map shows, updated as you pan and filter.",
        placement: "left",
      },
    ],
  },
  {
    id: "page-admin-engagement",
    kind: "page",
    route: "/admin/engagement",
    label: "Engagement",
    steps: [
      {
        anchor: '[data-tour-id="engagement-tabs"]',
        title: "Three lenses",
        body: "Overview for the north star, drill-downs for each side of the market.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="engagement-northstar"]',
        title: "The north star",
        body: "One number for marketplace health, with the lenses that feed it below.",
        placement: "bottom",
      },
      {
        anchor: '[data-tour-id="engagement-funnels"]',
        title: "Activation funnels",
        body: "Signup to transacting for workers, onboarding to first hire for employers.",
        placement: "top",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Persona walkthroughs — curated, cross-page, one per role
// ---------------------------------------------------------------------------

const WALKTHROUGHS: Tour[] = [
  {
    id: "walkthrough-applicant",
    kind: "walkthrough",
    role: "applicant",
    label: "Welcome tour",
    steps: [
      {
        route: "/applicant",
        anchor: 'a[href="/applicant/matches"]',
        title: "Start with matches",
        body: "Jobs ranked against your profile, with the score and the reasons. This is the heart of SKILLED.",
        placement: "right",
      },
      {
        route: "/applicant/matches",
        anchor: '[data-tour-id="matches-summary"]',
        title: "Your list, in one line",
        body: "How many jobs are ready now and how many are close. It updates as your profile improves.",
        placement: "bottom",
      },
      {
        route: "/applicant/matches",
        anchor: '[data-tour-id="matches-ready"]',
        title: "Ready to apply",
        body: "You meet every requirement for these jobs. Open one to see the breakdown and apply.",
        placement: "bottom",
      },
      {
        route: "/applicant/applications",
        anchor: '[data-tour-id="applications-list"]',
        title: "Track what you send",
        body: "Applications land here with status, employer views, and interview requests.",
        placement: "bottom",
      },
      {
        route: "/applicant/credentials",
        anchor: '[data-tour-id="credentials-add"]',
        title: "Make yourself verifiable",
        body: "Add your certifications and licenses. We check them against real registries so employers see proof.",
        placement: "bottom",
      },
      {
        route: "/applicant/credentials",
        anchor: 'a[href="/applicant/chat"]',
        title: "When you want a plan",
        body: "The planning chat maps the path to a job you care about. That is the tour. The grey icon on any page replays its own.",
        placement: "right",
      },
    ],
  },
  {
    id: "walkthrough-employer",
    kind: "walkthrough",
    role: "employer",
    label: "Welcome tour",
    steps: [
      {
        route: "/employer",
        anchor: '[data-tour-id="employer-today"]',
        title: "Your day starts here",
        body: "New applications and careers-page sync health in one list.",
        placement: "bottom",
      },
      {
        route: "/employer/jobs/add",
        anchor: '[data-tour-id="post-single"]',
        title: "Post your first job",
        body: "Write one role in a few minutes. It starts matching as soon as it publishes.",
        placement: "bottom",
      },
      {
        route: "/employer/jobs/add",
        anchor: '[data-tour-id="post-import"]',
        title: "Or bring them all",
        body: "Import from a careers URL, a CSV, or a pasted list. You approve each row before it goes live.",
        placement: "bottom",
      },
      {
        route: "/employer/applications",
        anchor: '[data-tour-id="apps-buckets"]',
        title: "Applications arrive here",
        body: "New, in review, interview, decided. Work left to right.",
        placement: "bottom",
      },
      {
        route: "/employer/verified-workers",
        anchor: '[data-tour-id="workers-filters"]',
        title: "Search verified workers",
        body: "Registry-verified credentials, consented visibility. Reach out before they apply.",
        placement: "bottom",
      },
      {
        route: "/employer/analytics",
        anchor: '[data-tour-id="analytics-next"]',
        title: "Analytics keeps score",
        body: "What is waiting on you and how the pipeline is moving. The grey icon on any page replays its own tour.",
        placement: "bottom",
      },
    ],
  },
  {
    id: "walkthrough-admin",
    kind: "walkthrough",
    role: "admin",
    label: "Welcome tour",
    steps: [
      {
        route: "/admin",
        anchor: '[data-tour-id="admin-priority"]',
        title: "The morning read",
        body: "Everything waiting on a human: imports, review items, credentials.",
        placement: "bottom",
      },
      {
        route: "/admin/job-imports",
        anchor: '[role="tablist"][aria-label="Batch filters"]',
        title: "Approve what goes live",
        body: "Employer batches and careers-page pulls. Approving publishes to the live board.",
        placement: "bottom",
      },
      {
        route: "/admin/review",
        anchor: '[role="tablist"][aria-label="Item types"]',
        title: "Judgment calls",
        body: "Whatever the pipelines could not settle lands here, prioritized.",
        placement: "bottom",
      },
      {
        route: "/admin/matching",
        anchor: '[data-tour-id="matching-weights"]',
        title: "The ranking rules",
        body: "Weights, gates, and relaxation. Preview the shift before you activate. Every change is versioned and audited.",
        placement: "bottom",
      },
      {
        route: "/admin/engagement",
        anchor: '[data-tour-id="engagement-tabs"]',
        title: "How the marketplace is doing",
        body: "One north star, funnels for each side, drill-downs when you need names. The grey icon on any page replays its own tour.",
        placement: "bottom",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Registry + lookups
// ---------------------------------------------------------------------------

export const TOURS: Tour[] = [
  ...APPLICANT_PAGE_TOURS,
  ...EMPLOYER_PAGE_TOURS,
  ...ADMIN_PAGE_TOURS,
  ...WALKTHROUGHS,
];

const BY_ID = new Map(TOURS.map((t) => [t.id, t]));
const BY_ROUTE = new Map(
  TOURS.filter((t) => t.kind === "page" && t.route).map((t) => [t.route as string, t]),
);
const BY_ROLE = new Map(
  TOURS.filter((t) => t.kind === "walkthrough" && t.role).map((t) => [t.role as string, t]),
);

export function getTour(id: string): Tour | null {
  return BY_ID.get(id) ?? null;
}

/** The page tour registered for an exact pathname, if any. */
export function pageTourFor(pathname: string): Tour | null {
  return BY_ROUTE.get(pathname) ?? null;
}

/** The cross-page walkthrough for a role, if any. */
export function walkthroughFor(role: string): Tour | null {
  return BY_ROLE.get(role) ?? null;
}

/** Dashboard roots where the tour icon also offers the full walkthrough. */
export const DASHBOARD_ROOTS = new Set(["/applicant", "/employer", "/admin"]);
