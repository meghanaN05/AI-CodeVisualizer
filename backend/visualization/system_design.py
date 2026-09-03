"""System-design agent — architecture DSL, not a generic graph."""

from __future__ import annotations

from typing import Any

from visualization.schema import Chapter, DslEdge, DslNode, DslStep, VisualizationDocument


TWITTER_COMPONENTS = [
    ("client", "Mobile/Web Client", "client"),
    ("gateway", "API Gateway", "gateway"),
    ("lb", "Load Balancer", "gateway"),
    ("tweet", "Tweet Service", "service"),
    ("fanout", "Fanout Service", "service"),
    ("timeline", "Timeline Service", "service"),
    ("cache", "Redis Cache", "cache"),
    ("queue", "Message Queue", "queue"),
    ("db", "Tweet DB", "database"),
]

TWITTER_CONNECTIONS = [
    ("client", "gateway"),
    ("gateway", "lb"),
    ("lb", "tweet"),
    ("tweet", "db"),
    ("tweet", "queue"),
    ("queue", "fanout"),
    ("fanout", "timeline"),
    ("timeline", "cache"),
]


def plan_system_design(ir: dict[str, Any]) -> VisualizationDocument:
    class_name = "Twitter"
    if ir.get("classes"):
        class_name = ir["classes"][0].get("name") or class_name
    methods = [m.get("name") for m in ir.get("methods") or [] if m.get("name")]
    if not methods:
        methods = ["postTweet", "getNewsFeed", "follow", "unfollow"]

    components = [
        DslNode(id=cid, label=label, category=cat) for cid, label, cat in TWITTER_COMPONENTS
    ]
    connections = [DslEdge(**{"from": a, "to": b}) for a, b in TWITTER_CONNECTIONS]

    chapters = [
        Chapter(
            id="requirements",
            title="Problem requirements",
            steps=[
                DslStep(action="show_title", text=f"Design {class_name}"),
                DslStep(
                    action="show_class_methods",
                    text=class_name,
                    nodes=methods,
                    caption="post, follow, and generate a ranked news feed",
                ),
            ],
        ),
        Chapter(
            id="architecture",
            title="High-level architecture",
            steps=[
                DslStep(
                    action="show_architecture",
                    caption="Layered Twitter architecture — layout computed by the engine",
                ),
            ],
        ),
        Chapter(
            id="create",
            title="Tweet creation",
            steps=[
                DslStep(action="highlight_component", component="client", caption="Client posts a tweet"),
                DslStep(action="show_flow", **{"from": "client", "to": "gateway"}),
                DslStep(action="show_flow", **{"from": "gateway", "to": "tweet"}),
                DslStep(
                    action="show_hashmap",
                    text="tweets",
                    values=[["user 1", "[(t0,101)]"], ["user 2", "[(t0,201)]"]],
                    caption="Tweet Service writes (timestamp, tweetId) to storage",
                ),
                DslStep(action="highlight_component", component="db", caption="Persist tweet in Tweet DB"),
            ],
        ),
        Chapter(
            id="fanout",
            title="Fanout",
            steps=[
                DslStep(action="show_flow", **{"from": "tweet", "to": "queue"}, caption="Publish to queue"),
                DslStep(action="highlight_component", component="fanout", caption="Fanout to followers"),
                DslStep(
                    action="show_graph",
                    nodes=["User1", "User2", "User3"],
                    caption="Follow graph: who receives this tweet",
                ),
            ],
        ),
        Chapter(
            id="timeline",
            title="Timeline generation",
            steps=[
                DslStep(action="highlight_component", component="timeline", caption="Assemble home timeline"),
                DslStep(
                    action="show_heap",
                    values=[("(t2,103)", 103), ("(t1,102)", 102), ("(t0,201)", 201)],
                    caption="Merge recent tweets with a max-heap / priority queue",
                ),
                DslStep(action="heap_pop", label="103", caption="Pop the 10 most recent tweet IDs"),
            ],
        ),
        Chapter(
            id="scale",
            title="Scaling",
            steps=[
                DslStep(action="highlight_component", component="cache", caption="Cache hot timelines in Redis"),
                DslStep(action="highlight_component", component="lb", caption="Scale tweet service behind a load balancer"),
                DslStep(action="show_caption", text="Final architecture: write path + fanout + cached read path"),
            ],
        ),
    ]

    steps: list[DslStep] = []
    for chapter in chapters:
        steps.append(DslStep(action="chapter", chapter=chapter.title, text=chapter.title))
        steps.extend(chapter.steps)

    return VisualizationDocument(
        domain="system_design",
        type="architecture",
        algorithm="twitter_design",
        title=f"Design {class_name}",
        data_structure="architecture",
        description="Architecture visualization with per-chapter layouts",
        components=components,
        connections=connections,
        chapters=chapters,
        steps=steps,
    )
