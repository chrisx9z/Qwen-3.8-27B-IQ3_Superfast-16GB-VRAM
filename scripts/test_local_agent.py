from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.controller import AgentConfig, LocalAgent
from agent.tools import LocalToolRegistry
from llm.server_manager import LocalLLMServerManager


class StubAgent(LocalAgent):
    def __init__(self) -> None:
        super().__init__(
            config=AgentConfig(
                auto_start_server=True,
                model_profile="qwen38_iq3s",
            )
        )
        self.profiles: list[str] = []
        self.responses = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {
                            "name": "list_projects",
                            "arguments": "{\"limit\":1}",
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "Đã kiểm tra project.",
            },
        ]

    def _ensure_server(self, profile: str) -> None:
        self.profiles.append(profile)

    def _chat(
        self,
        messages: list[dict],
        tool_definitions: list[dict],
        max_tokens: int,
        abort_check: Any = None,
    ) -> dict:
        return self.responses.pop(0)


def main() -> int:
    config = AgentConfig(auto_start_server=False)
    assert config.server_port == 8080
    assert config.endpoint.endswith(":8080/v1/chat/completions")
    assert config.model_profile == "qwen38_iq3s"

    manager = LocalLLMServerManager(
        profile="qwen38_iq3s",
        port=8080,
    )
    command = manager._build_command()
    assert command[command.index("--port") + 1] == "8080"
    assert "--model" in command

    registry = LocalToolRegistry()
    assert len(registry.definitions()) == 295
    assert registry.execute(
        "swarm_multi_agent_deep_investigation",
        {"topic": "Qwen 3.8 27B Local Performance Optimization", "focus": "Technical Architecture"},
    )["ok"]
    assert registry.execute(
        "track_trending_industry_topics_radar",
        {"category": "ai_tech"},
    )["ok"]
    assert registry.execute(
        "generate_executive_research_briefing_pdf_md",
        {"topic": "Test Briefing", "summary": "Summary", "findings": "Findings", "recommendations": "Recs"},
    )["ok"]
    assert registry.execute(
        "store_research_knowledge_item",
        {"topic": "Qwen 27B Architecture", "insight": "IQ3_S quantization preserves 99% accuracy.", "tags": ["qwen", "ai"]},
    )["ok"]
    assert registry.execute(
        "retrieve_relevant_research_knowledge",
        {"query": "qwen"},
    )["ok"]
    assert registry.execute(
        "evaluate_source_authority_and_recency",
        {"url": "https://arxiv.org/abs/2401.0001"},
    )["ok"]
    assert registry.execute(
        "generate_counterfactual_hypotheses_and_insights",
        {"decision_or_strategy": "Migrate to FlashAttention-2 for 2x faster inference"},
    )["ok"]
    assert registry.execute(
        "autonomous_multi_hop_research",
        {"topic": "Qwen 3.8 27B AI Architecture", "depth": "fast"},
    )["ok"]
    assert registry.execute(
        "crawl_and_extract_deep_content",
        {"url": "https://www.google.com"},
    )["ok"]
    assert registry.execute(
        "cross_reference_and_fact_check",
        {"claim_or_topic": "FlashAttention-2 improves memory throughput"},
    )["ok"]
    assert registry.execute(
        "deep_dive_internet_research",
        {"topic_or_query": "Chiến lược tăng trưởng YouTube 2026", "max_sources": 2},
    )["ok"]
    assert registry.execute(
        "analyze_youtube_channel_deep_dive",
        {"query_or_url": "nini vietsub"},
    )["ok"]
    assert registry.execute(
        "inject_chrome_userscript_extension",
        {"script_payload": "console.log('injected');", "run_at": "document_start"},
    )["ok"]
    assert registry.execute(
        "bridge_windows_clipboard_data",
        {"action": "read_text"},
    )["ok"]
    assert registry.execute(
        "enforce_computer_action_safety_firewall",
        {"action_intent": "Mở ứng dụng Notepad"},
    )["ok"]
    assert registry.execute(
        "swap_chrome_isolated_profiles",
        {"profile_name": "WorkProfile"},
    )["ok"]
    assert registry.execute(
        "search_and_click_screen_text_ocr",
        {"target_text": "Tìm kiếm"},
    )["ok"]
    assert registry.execute(
        "execute_end_to_end_computer_mission",
        {"mission_prompt": "Mở Chrome và tải báo cáo doanh thu"},
    )["ok"]
    assert registry.execute(
        "observe_chrome_dom_network_events",
        {"event_type": "network_idle"},
    )["ok"]
    assert registry.execute(
        "switch_windows_virtual_desktop_monitor",
        {"desktop_index": 2},
    )["ok"]
    assert registry.execute(
        "autofill_semantic_forms_with_vision_ocr",
        {"form_data": {"name": "Admin", "email": "admin@example.com"}},
    )["ok"]
    assert registry.execute(
        "manage_chrome_multitab_cookies",
        {"action": "list_tabs"},
    )["ok"]
    assert registry.execute(
        "manipulate_windows_window_hierarchy",
        {"window_title": "Chrome", "action": "bring_to_front"},
    )["ok"]
    assert registry.execute(
        "ground_screen_visual_bounding_boxes",
        {"target_element_prompt": "Nút Đăng nhập"},
    )["ok"]
    assert registry.execute(
        "execute_resilient_computer_action_loop",
        {"goal_description": "Tải tài liệu từ web", "retry_limit": 3},
    )["ok"]
    assert registry.execute(
        "control_windows_native_human_input",
        {"action_type": "smooth_move_and_click", "x": 640, "y": 480},
    )["ok"]
    assert registry.execute(
        "locate_visual_screen_anchor_elements",
        {"visual_query": "search_button"},
    )["ok"]
    assert registry.execute(
        "orchestrate_autonomous_computer_task",
        {"task_objective": "Tự động hóa tác vụ trên máy tính"},
    )["ok"]
    assert registry.execute(
        "verify_qt_signal_slot_integrity",
        {},
    )["ok"]
    assert registry.execute(
        "benchmark_e2e_agent_workflow_latency",
        {"benchmark_steps": 4},
    )["ok"]
    assert registry.execute(
        "manage_zero_allocation_buffer_arena",
        {"arena_size_mb": 64},
    )["ok"]
    assert registry.execute(
        "audit_pyside6_qt_memory_leaks",
        {},
    )["ok"]
    assert registry.execute(
        "query_hybrid_vector_bm25_memory",
        {"semantic_query": "Tìm kiếm cơ chế kết nối LLM"},
    )["ok"]
    assert registry.execute(
        "summarize_longterm_codebase_knowledge",
        {"module_scope": "global_system"},
    )["ok"]
    assert registry.execute(
        "restart_llm_server_with_safe_fallback",
        {"safe_ctx_size": 8192},
    )["ok"]
    assert registry.execute(
        "monitor_llm_health_watchdog",
        {"probe_interval_ms": 250},
    )["ok"]
    assert registry.execute(
        "solve_backward_chaining_goals",
        {"target_goal_state": "Hệ thống vận hành tối ưu"},
    )["ok"]
    assert registry.execute(
        "check_symbolic_code_invariants_smt",
        {"target_function": "core_engine"},
    )["ok"]
    assert registry.execute(
        "verify_formal_contract_assertions",
        {"contract_scope": "mutation_safety"},
    )["ok"]
    assert registry.execute(
        "synthesize_counterfactual_critique",
        {"proposed_solution": "Tối ưu hóa pipeline"},
    )["ok"]
    assert registry.execute(
        "verify_strict_invariant_constraints",
        {"target_component": "codebase_integrity"},
    )["ok"]
    assert registry.execute(
        "audit_reasoning_trajectory_fidelity",
        {"trajectory_depth": 5},
    )["ok"]
    assert registry.execute(
        "index_inmemory_ast_symbol_cache",
        {"cache_target_path": "agent/"},
    )["ok"]
    assert registry.execute(
        "accelerate_zero_gap_tool_pipeline",
        {"prefetch_environment": True},
    )["ok"]
    assert registry.execute(
        "swap_hierarchical_kv_cache_tiers",
        {"tier_target": "auto"},
    )["ok"]
    assert registry.execute(
        "boost_tensorcore_gemm_inference",
        {"tile_strategy": "128x128x64"},
    )["ok"]
    assert registry.execute(
        "prefetch_async_layer_weights",
        {"prefetch_streams_count": 2},
    )["ok"]
    assert registry.execute(
        "decode_adaptive_early_exit_tokens",
        {"confidence_threshold": 0.995},
    )["ok"]
    assert registry.execute(
        "broadcast_gqa_sram_cache",
        {"sram_tile_kb": 128},
    )["ok"]
    assert registry.execute(
        "accelerate_ngram_speculative_decoding",
        {"draft_tokens_count": 6},
    )["ok"]
    assert registry.execute(
        "maximize_4bit_kv_cache_bandwidth",
        {"kv_quant_mode": "q4_0"},
    )["ok"]
    assert registry.execute(
        "configure_tcp_nodelay_token_stream",
        {"buffer_flush_interval_ms": 0},
    )["ok"]
    assert registry.execute(
        "route_dynamic_tool_schema",
        {"task_intent": "coding"},
    )["ok"]
    assert registry.execute(
        "overlap_async_gpu_io_pipeline",
        {"queue_depth": 4},
    )["ok"]
    assert registry.execute(
        "audit_final_classvar_immutability",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "generate_github_ci_matrix_workflow",
        {"workflow_file": ".github/workflows/ci.yml"},
    )["ok"]
    assert registry.execute(
        "audit_contextvar_thread_safety",
        {"path": "agent/controller.py"},
    )["ok"]
    assert registry.execute(
        "generate_semver_release_tag",
        {"current_tag": "v1.4.0", "release_type": "patch"},
    )["ok"]
    assert registry.execute(
        "audit_paramspec_decorator_safety",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "switch_semantic_git_worktree",
        {"action": "list"},
    )["ok"]
    assert registry.execute(
        "audit_typeguard_narrowing_safety",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "generate_semantic_branch_name",
        {"category": "feature", "description": "tensor parallel sharding"},
    )["ok"]
    assert registry.execute(
        "audit_enum_flag_exhaustiveness",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "harden_docker_compose_production",
        {"compose_file": "docker-compose.yml"},
    )["ok"]
    assert registry.execute(
        "audit_asyncio_taskgroup_safety",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "verify_db_migration_rollback",
        {"migration_file": "migrations/0001_initial.sql"},
    )["ok"]
    assert registry.execute(
        "audit_pydantic_v2_migration",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "run_git_prepush_matrix",
        {},
    )["ok"]
    assert registry.execute(
        "validate_typeddict_totality",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "generate_openapi_sdk_client",
        {"api_name": "test_sdk_client"},
    )["ok"]
    assert registry.execute(
        "audit_protocol_structural_subtypes",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "manage_workspace_backup_vault",
        {"action": "create_snapshot", "tag": "test_milestone"},
    )["ok"]
    assert registry.execute(
        "audit_async_generator_safety",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "visualize_monorepo_dependency_graph",
        {"include_external": False},
    )["ok"]
    assert registry.execute(
        "validate_typevar_variance",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "migrate_git_lfs_pointers",
        {"threshold_mb": 50},
    )["ok"]
    assert registry.execute(
        "audit_unreachable_code",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "sync_multi_git_remotes",
        {"remotes": ["origin", "backup"]},
    )["ok"]
    assert registry.execute(
        "validate_match_case_exhaustiveness",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "bump_semantic_version",
        {"current_version": "1.4.0", "bump_type": "patch"},
    )["ok"]
    assert registry.execute(
        "detect_dead_class_members",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "audit_git_commit_signatures",
        {"max_commits": 5},
    )["ok"]
    assert registry.execute(
        "audit_context_manager_safety",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "sync_git_submodules_recursive",
        {"remote": False},
    )["ok"]
    assert registry.execute(
        "audit_generator_yield_return",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "manage_git_patches",
        {"action": "export"},
    )["ok"]
    assert registry.execute(
        "inspect_git_revert_safety",
        {"commit_range": "HEAD~3..HEAD"},
    )["ok"]
    assert registry.execute(
        "resolve_markdown_footnotes",
        {"content": "Text with footnote[^1] and [^2].\n\n[^1]: Note 1\n[^2]: Note 2"},
    )["ok"]
    assert registry.execute(
        "manage_git_worktrees",
        {"action": "list"},
    )["ok"]
    assert registry.execute(
        "beautify_markdown_callouts",
        {"content": "Note: This is a note.\nWarning: Be careful."},
    )["ok"]
    assert registry.execute(
        "simulate_git_rebase_conflicts",
        {"upstream_branch": "main"},
    )["ok"]
    assert registry.execute(
        "align_markdown_table_columns",
        {"raw_table": "| Name | Status | Tokens |\n|---|---|---|\n| Task | Done | 1500 |"},
    )["ok"]
    assert registry.execute(
        "detect_async_deadlocks",
        {"path": "agent/controller.py"},
    )["ok"]
    assert registry.execute(
        "generate_markdown_badges",
        {"tools_count": 170},
    )["ok"]
    assert registry.execute(
        "generate_type_guards",
        {"type_name": "UserPayload"},
    )["ok"]
    assert registry.execute(
        "assist_git_cherry_pick",
        {"commit_hash": "a1b2c3d4e5f6"},
    )["ok"]
    assert registry.execute(
        "audit_exception_hierarchy",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "validate_markdown_code_blocks",
        {"path": "README.md"},
    )["ok"]
    assert registry.execute(
        "advise_complexity_refactoring",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "check_code_spelling",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "check_global_variable_pollution",
        {"path": "agent/controller.py"},
    )["ok"]
    assert registry.execute(
        "generate_markdown_toc",
        {"content": "# Heading 1\n## Heading 2\n### Heading 3"},
    )["ok"]
    assert registry.execute(
        "detect_circular_imports",
        {"root_folder": "agent"},
    )["ok"]
    assert registry.execute(
        "cleanup_stale_git_branches",
        {"dry_run": True},
    )["ok"]
    assert registry.execute(
        "simulate_flamegraph_profile",
        {"entry_function": "run_prompt_loop"},
    )["ok"]
    assert registry.execute(
        "generate_semantic_commit_msg",
        {"scope": "agent", "summary": "Nâng cấp bộ công cụ lên 152 tools"},
    )["ok"]
    assert registry.execute(
        "visualize_dependency_graph",
        {"root_folder": "agent"},
    )["ok"]
    assert registry.execute(
        "validate_markdown_links",
        {"path": "GHI_CHU_THAY_DOI.txt"},
    )["ok"]
    assert registry.execute(
        "audit_docstring_coverage",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "diagnose_workspace_health",
        {},
    )["ok"]
    assert registry.execute(
        "analyze_taint_flow_security",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "format_markdown_table",
        {"raw_table": "| col1 | col2 |\n|---|---|\n| 1 | 2 |"},
    )["ok"]
    assert registry.execute(
        "generate_sqlite_migration",
        {"table_name": "users", "new_columns": ["email TEXT"]},
    )["ok"]
    assert registry.execute(
        "refactor_python_code",
        {"code": "def test():\n    res = []\n    for i in range(5):\n        res.append(i)\n    return res"},
    )["ok"]
    assert registry.execute(
        "recommend_semver_bump",
        {"current_version": "2.5.0"},
    )["ok"]
    assert registry.execute(
        "clean_dead_imports",
        {"path": "agent/tools.py", "dry_run": True},
    )["ok"]
    assert registry.execute(
        "profile_network_bandwidth",
        {},
    )["ok"]
    assert registry.execute(
        "convert_regex_to_railroad",
        {"pattern": r"\w+"},
    )["ok"]
    assert registry.execute(
        "audit_dependency_cve",
        {},
    )["ok"]
    assert registry.execute(
        "format_python_source",
        {"path": "agent/tools.py", "dry_run": True},
    )["ok"]
    assert registry.execute(
        "simulate_cron_schedule",
        {"cron_expression": "0 2 * * *"},
    )["ok"]
    assert registry.execute(
        "profile_memory_leaks",
        {},
    )["ok"]
    assert registry.execute(
        "benchmark_regex_pattern",
        {"pattern": r"\d+", "test_string": "abc 123 def 456"},
    )["ok"]
    assert registry.execute(
        "calculate_code_complexity",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "audit_license_compliance",
        {},
    )["ok"]
    assert registry.execute(
        "manage_code_snippets",
        {"action": "list"},
    )["ok"]
    assert registry.execute(
        "localize_i18n_strings",
        {"action": "scan"},
    )["ok"]
    assert registry.execute(
        "clean_workspace_cache",
        {"dry_run": True},
    )["ok"]
    assert registry.execute(
        "detect_code_duplicates",
        {"root_folder": "core"},
    )["ok"]
    assert registry.execute(
        "profile_gpu_hardware",
        {},
    )["ok"]
    assert registry.execute(
        "generate_slide_deck",
        {"title": "M Auto Pilot", "topic": "AI Coding"},
    )["ok"]
    assert registry.execute(
        "diagnose_environment_doctor",
        {},
    )["ok"]
    assert registry.execute(
        "audit_security_vulnerabilities",
        {"root_folder": "core"},
    )["ok"]
    assert registry.execute(
        "resolve_merge_conflicts",
        {"strategy": "analyze"},
    )["ok"]
    assert registry.execute(
        "manage_git_stash",
        {"action": "list"},
    )["ok"]
    assert registry.execute(
        "generate_mermaid_diagram",
        {"diagram_type": "flowchart", "path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "cache_tokenized_vocabulary",
        {},
    )["ok"]
    assert registry.execute(
        "analyze_streaming_latency",
        {},
    )["ok"]
    assert registry.execute(
        "calculate_token_budget",
        {"text": "def hello(): print('world')"},
    )["ok"]
    assert registry.execute(
        "memoize_llm_response",
        {"action": "stats"},
    )["ok"]
    assert registry.execute(
        "auto_prune_context_window",
        {"max_history_turns": 6},
    )["ok"]
    assert registry.execute(
        "tune_cuda_streams",
        {},
    )["ok"]
    assert registry.execute(
        "manage_kv_cache",
        {"action": "inspect"},
    )["ok"]
    assert registry.execute(
        "optimize_llm_inference",
        {},
    )["ok"]
    assert registry.execute(
        "smart_prompt_compressor",
        {"text": "Hello   world \n\n  test  "},
    )["ok"]
    assert registry.execute(
        "generate_openapi_schema",
        {"title": "Test API", "version": "1.0.0"},
    )["ok"]
    assert registry.execute(
        "calculate_code_metrics",
        {"root_folder": "core"},
    )["ok"]
    assert registry.execute(
        "encode_decode_data",
        {"text": "Hello M Auto Pilot", "action": "base64_encode"},
    )["ok"]
    assert registry.execute(
        "clean_dead_code",
        {"path": "core", "apply_fix": False},
    )["ok"]
    assert registry.execute(
        "generate_dockerfile",
        {"app_type": "python_fastapi", "port": 8000, "save_to_workspace": False},
    )["ok"]
    assert registry.execute(
        "minify_code_assets",
        {"content": '{"app": "test", "num": 123}', "language": "json"},
    )["ok"]
    assert registry.execute(
        "benchmark_code_performance",
        {"code": "x = [i**2 for i in range(100)]", "iterations": 10},
    )["ok"]
    assert registry.execute(
        "inspect_system_processes",
        {"filter_name": "python"},
    )["ok"]
    assert registry.execute(
        "calculate_file_checksum",
        {"path": "agent/tools.py", "algorithm": "sha256"},
    )["ok"]
    assert registry.execute(
        "scan_local_ports",
        {"ports": [8080, 8000]},
    )["ok"]
    assert registry.execute(
        "detect_code_smells",
        {"root_folder": "core"},
    )["ok"]
    assert registry.execute(
        "manage_env_secrets",
        {"action": "scan_secrets"},
    )["ok"]
    assert registry.execute(
        "generate_project_docs",
        {"root_folder": "core"},
    )["ok"]
    assert registry.execute(
        "convert_config_format",
        {"content": '{"name": "test", "val": 123}', "from_format": "json", "to_format": "yaml"},
    )["ok"]
    assert registry.execute(
        "generate_architecture_map",
        {"max_depth": 2},
    )["ok"]
    assert registry.execute(
        "format_and_lint_code",
        {"path": "core", "fix": False},
    )["ok"]
    assert registry.execute(
        "manage_dependencies",
        {"action": "list"},
    )["ok"]
    assert registry.execute(
        "run_python_code",
        {"code": "print('hello from sandbox')"},
    )["ok"]
    assert registry.execute(
        "list_checkpoints",
        {"limit": 5},
    )["ok"]
    assert registry.execute(
        "update_task_plan",
        {"items": [{"title": "Test step 1", "status": "completed"}]},
    )["ok"]
    assert registry.execute(
        "manage_memory",
        {"action": "read"},
    )["ok"]
    assert registry.execute(
        "get_workspace_info",
        {},
    )["ok"]
    assert registry.execute(
        "check_code_syntax",
        {"language": "python", "content": "x = 1\ny = 2\n"},
    )["ok"]
    assert not registry.execute(
        "check_code_syntax",
        {"language": "python", "content": "def foo(:\n    pass\n"},
    )["ok"]
    assert registry.execute(
        "get_directory_tree",
        {"path": "agent", "max_depth": 2},
    )["ok"]
    assert registry.execute(
        "git_log",
        {"limit": 3},
    )["ok"]
    assert registry.execute(
        "git_branch",
        {"action": "list"},
    )["ok"]
    assert registry.execute(
        "git_stash",
        {"action": "list"},
    )["ok"]
    assert not registry.execute(
        "browser_open",
        {"url": "file:///not-allowed"},
    )["ok"]
    assert not registry.execute(
        "browser_snapshot",
        {},
    )["ok"]
    assert not registry.execute(
        "ui_press_key",
        {"window_title": "missing", "key": "F1"},
    )["ok"]
    assert not registry.execute(
        "ui_click_text",
        {"text": "nonexistent_button_text_123"},
    )["ok"]
    assert registry.execute(
        "list_processes",
        {"name": "python", "limit": 5},
    )["ok"]
    assert registry.execute(
        "get_resource_status",
        {},
    )["ok"]
    assert not registry.execute(
        "screen_ocr",
        {"image_path": "C:\\Windows\\not-allowed.png"},
    )["ok"]
    assert registry.execute(
        "read_code_file",
        {"path": "agent/controller.py", "max_chars": 2000},
    )["ok"]
    assert registry.execute(
        "search_code",
        {"query": "class LocalAgent", "path": "agent"},
    )["ok"]
    assert registry.execute(
        "git_status",
        {},
    )["ok"]
    assert registry.execute(
        "git_diff",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "run_code_check",
        {"kind": "compile", "path": "agent/controller.py"},
    )["ok"]
    checkpoint = registry.execute(
        "create_checkpoint",
        {"paths": ["agent/controller.py"]},
    )
    assert checkpoint["ok"]
    assert registry.execute(
        "restore_checkpoint",
        {"checkpoint_id": checkpoint["result"]["checkpoint_id"]},
    )["ok"]
    assert registry.execute(
        "list_directory",
        {"path": "agent", "limit": 5},
    )["ok"]
    assert registry.execute(
        "get_system_status",
        {},
    )["ok"]
    assert not registry.execute(
        "run_project_stage",
        {"project_id": "missing", "stage": "invalid"},
    )["ok"]
    assert not registry.execute(
        "download_bilibili",
        {"url": "https://example.com"},
    )["ok"]

    # Test StreamTagRouter
    from agent.controller import StreamTagRouter
    emitted: list[tuple[str, dict]] = []
    router = StreamTagRouter(lambda evt, payload: emitted.append((evt, payload)))
    router.feed_content("Xin chào <think>Tôi đang suy")
    router.feed_content(" nghĩ về câu hỏi</think> đây là câu trả lời.")
    router.flush()
    assert router.final_reasoning == "Tôi đang suy nghĩ về câu hỏi"
    assert router.final_content == "Xin chào  đây là câu trả lời."

    agent = StubAgent()
    result = agent.run(
        "Liệt kê project.",
        model_profile="q6",
    )

    assert result.text == "Đã kiểm tra project."
    assert result.steps == 2
    # Mọi profile cũ (Q4/Q6/14B) đều quy về model duy nhất IQ3_S.
    assert agent.profiles == ["qwen38_iq3s"]
    print("local-agent tool-loop/profile: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
