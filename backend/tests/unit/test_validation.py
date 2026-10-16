from app.services.validation import find_cycle


def test_no_dependencies_no_cycle():
    assert find_cycle(1, [], {}) is None


def test_chain_without_cycle():
    # 1 will depend on 2; 2 depends on 3
    assert find_cycle(1, [2], {2: {3}}) is None


def test_direct_cycle():
    # 1 will depend on 2, and 2 already depends on 1
    assert find_cycle(1, [2], {2: {1}}) == [1, 2, 1]


def test_indirect_cycle():
    path = find_cycle(1, [2], {2: {3}, 3: {4}, 4: {1}})
    assert path == [1, 2, 3, 4, 1]


def test_self_dependency_is_a_cycle():
    assert find_cycle(1, [1], {}) == [1, 1]


def test_diamond_is_not_a_cycle():
    edges = {2: {4}, 3: {4}}
    assert find_cycle(1, [2, 3], edges) is None


def test_cycle_elsewhere_in_the_graph_does_not_loop_forever():
    # 5 <-> 6 is a cycle that never reaches 1
    assert find_cycle(1, [5], {5: {6}, 6: {5}}) is None


def test_only_one_of_several_targets_closes_the_cycle():
    assert find_cycle(1, [2, 3], {3: {1}}) == [1, 3, 1]
