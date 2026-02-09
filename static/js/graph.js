/* ============================================================
   Megregore — Memory Graph Page (D3.js Force-Directed)
   ============================================================ */

App.registerPage('graph', async () => {
    const data = await App.api('/graph', { limit: 150 });
    App._graphData = data;  // Stash for graph_init to avoid double fetch
    const nodes = data.nodes || [];
    const edges = data.edges || [];

    if (!nodes.length) {
        return `
        <div class="page-header fade-in">
            <h1>Memory Graph</h1>
            <p>Connections between Echo's memories</p>
        </div>
        ${App.emptyState('No connections yet', 'Link memories together to see the graph come alive.')}`;
    }

    const typeColors = {
        experience:  '#7c5bf5',
        fact:        '#3b82f6',
        observation: '#06b6d4',
        reflection:  '#a78bfa',
        insight:     '#f59e0b',
        emotion:     '#ec4899',
    };

    const linkColors = {
        related:      '#6b7280',
        caused_by:    '#3b82f6',
        evolved_from: '#7c5bf5',
        contradicts:  '#f87171',
    };

    // Legend HTML
    const typeLegend = Object.entries(typeColors).map(([type, color]) =>
        `<span class="legend-item"><span class="legend-dot" style="background:${color}"></span>${type}</span>`
    ).join('');

    const linkLegend = Object.entries(linkColors).map(([type, color]) =>
        `<span class="legend-item"><span class="legend-dot" style="background:${color};border-radius:2px;width:16px;height:4px;"></span>${type.replace('_', ' ')}</span>`
    ).join('');

    return `
    <div class="page-header fade-in">
        <h1>Memory Graph</h1>
        <p>${nodes.length} connected memories, ${edges.length} links</p>
    </div>
    <div class="graph-container fade-in" id="graph-container">
        <div class="graph-tooltip" id="graph-tooltip"></div>
        <svg id="graph-svg"></svg>
    </div>
    <div class="graph-legend fade-in">
        <span class="legend-item" style="font-weight:600;color:var(--text-primary);">Node types:</span>
        ${typeLegend}
        <span style="width:16px;"></span>
        <span class="legend-item" style="font-weight:600;color:var(--text-primary);">Link types:</span>
        ${linkLegend}
    </div>`;
});

App.registerPage('graph_init', () => {
    const svg = d3.select('#graph-svg');
    if (!svg.node()) return;

    const container = document.getElementById('graph-container');
    const tooltip = document.getElementById('graph-tooltip');
    const width = container.clientWidth;
    const height = 600;

    svg.attr('viewBox', [0, 0, width, height]);

    const typeColors = {
        experience:  '#7c5bf5',
        fact:        '#3b82f6',
        observation: '#06b6d4',
        reflection:  '#a78bfa',
        insight:     '#f59e0b',
        emotion:     '#ec4899',
    };

    const linkColors = {
        related:      '#6b7280',
        caused_by:    '#3b82f6',
        evolved_from: '#7c5bf5',
        contradicts:  '#f87171',
    };

    // Reuse data stashed by page renderer — avoids redundant fetch
    const data = App._graphData;
    if (!data) return;
    App._graphData = null;  // Clean up

    const nodes = data.nodes || [];
    const edges = data.edges || [];

    if (!nodes.length) return;

    // Build node map for lookups
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    // Filter edges to only those with valid nodes
    const validEdges = edges.filter(e => nodeMap.has(e.source) && nodeMap.has(e.target));

    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(validEdges).id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-200))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => 8 + d.importance * 2));

    // Zoom behavior
    const g = svg.append('g');
    svg.call(d3.zoom()
        .scaleExtent([0.2, 4])
        .on('zoom', (event) => g.attr('transform', event.transform))
    );

    // Draw edges
    const link = g.append('g')
        .selectAll('line')
        .data(validEdges)
        .join('line')
        .attr('class', 'graph-link')
        .attr('stroke', d => linkColors[d.link_type] || '#6b7280')
        .attr('stroke-width', d => 1 + (d.strength || 0.5) * 2);

    // Draw nodes
    const node = g.append('g')
        .selectAll('g')
        .data(nodes)
        .join('g')
        .attr('class', 'graph-node')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended)
        );

    node.append('circle')
        .attr('r', d => 6 + d.importance * 1.5)
        .attr('fill', d => typeColors[d.memory_type] || '#6b7280')
        .attr('stroke', '#1e1e2e')
        .attr('stroke-width', 1.5);

    // Labels for high-importance nodes
    node.filter(d => d.importance >= 7)
        .append('text')
        .attr('dx', d => 10 + d.importance)
        .attr('dy', 4)
        .text(d => {
            const tags = d.tags || [];
            return tags.length ? tags[0] : d.memory_type;
        });

    // Tooltip on hover
    node.on('mouseover', (event, d) => {
        const content = d.content || '';
        tooltip.innerHTML = `
            <div style="margin-bottom:4px;">
                <span class="type-badge ${d.memory_type}" style="font-size:0.65rem;">${d.memory_type}</span>
                <span class="muted text-xs" style="margin-left:6px;">importance: ${d.importance}/10</span>
            </div>
            <div style="font-size:0.78rem;">${App.escapeHtml(content)}</div>
            ${d.tags && d.tags.length ? `<div style="margin-top:4px;">${App.tagPills(d.tags)}</div>` : ''}
        `;
        tooltip.classList.add('visible');
    })
    .on('mousemove', (event) => {
        const rect = container.getBoundingClientRect();
        tooltip.style.left = (event.clientX - rect.left + 14) + 'px';
        tooltip.style.top = (event.clientY - rect.top - 10) + 'px';
    })
    .on('mouseout', () => {
        tooltip.classList.remove('visible');
    });

    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }

    function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }

    function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }
});
