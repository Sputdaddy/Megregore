/* ============================================================
   Megregore — Memory Graph Page (Vue Component)
   D3.js Force-Directed Graph Visualization
   ============================================================ */

megregoreApp.component('graph-page', {
    setup() {
        const loading = ref(true);
        const error = ref('');
        const nodes = ref([]);
        const edges = ref([]);
        let simulation = null;

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

        const typeLegend = computed(() =>
            Object.entries(typeColors).map(([type, color]) => ({ type, color }))
        );

        const linkLegend = computed(() =>
            Object.entries(linkColors).map(([type, color]) => ({ type: type.replace('_', ' '), color }))
        );

        async function loadData() {
            loading.value = true;
            error.value = '';
            try {
                const data = await App.api('/graph', { limit: 150 });
                nodes.value = data.nodes || [];
                edges.value = data.edges || [];
            } catch (err) {
                error.value = err.message;
            } finally {
                loading.value = false;
            }
        }

        function renderGraph() {
            if (typeof d3 === 'undefined') return;
            if (!nodes.value.length) return;

            const svg = d3.select('#graph-svg');
            if (!svg.node()) return;

            const container = document.getElementById('graph-container');
            const tooltip = document.getElementById('graph-tooltip');
            const width = container.clientWidth;
            const height = 600;

            svg.attr('viewBox', [0, 0, width, height]);

            const nodeMap = new Map(nodes.value.map(n => [n.id, n]));
            const validEdges = edges.value.filter(e => nodeMap.has(e.source) && nodeMap.has(e.target));

            simulation = d3.forceSimulation(nodes.value)
                .force('link', d3.forceLink(validEdges).id(d => d.id).distance(100))
                .force('charge', d3.forceManyBody().strength(-200))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(d => 8 + d.importance * 2));

            const g = svg.append('g');
            svg.call(d3.zoom()
                .scaleExtent([0.2, 4])
                .on('zoom', (event) => g.attr('transform', event.transform))
            );

            const link = g.append('g')
                .selectAll('line')
                .data(validEdges)
                .join('line')
                .attr('class', 'graph-link')
                .attr('stroke', d => linkColors[d.link_type] || '#6b7280')
                .attr('stroke-width', d => 1 + (d.strength || 0.5) * 2);

            const node = g.append('g')
                .selectAll('g')
                .data(nodes.value)
                .join('g')
                .attr('class', 'graph-node')
                .call(d3.drag()
                    .on('start', (event) => {
                        if (!event.active) simulation.alphaTarget(0.3).restart();
                        event.subject.fx = event.subject.x;
                        event.subject.fy = event.subject.y;
                    })
                    .on('drag', (event) => {
                        event.subject.fx = event.x;
                        event.subject.fy = event.y;
                    })
                    .on('end', (event) => {
                        if (!event.active) simulation.alphaTarget(0);
                        event.subject.fx = null;
                        event.subject.fy = null;
                    })
                );

            node.append('circle')
                .attr('r', d => 6 + d.importance * 1.5)
                .attr('fill', d => typeColors[d.memory_type] || '#6b7280')
                .attr('stroke', '#1e1e2e')
                .attr('stroke-width', 1.5);

            node.filter(d => d.importance >= 7)
                .append('text')
                .attr('dx', d => 10 + d.importance)
                .attr('dy', 4)
                .text(d => {
                    const tags = d.tags || [];
                    return tags.length ? tags[0] : d.memory_type;
                });

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
        }

        onMounted(async () => {
            await loadData();
            await nextTick();
            renderGraph();
        });

        onUnmounted(() => {
            if (simulation) { simulation.stop(); simulation = null; }
        });

        return { loading, error, nodes, edges, typeLegend, linkLegend };
    },

    template: `
        <div v-if="loading" class="loading"><div class="spinner"></div></div>

        <div v-else-if="error" class="empty-state fade-in">
            <h3>Something went wrong</h3>
            <p>{{ error }}</p>
        </div>

        <div v-else-if="!nodes.length" class="fade-in">
            <div class="page-header">
                <h1>Memory Graph</h1>
                <p>Connections between Echo's memories</p>
            </div>
            <div class="empty-state">
                <div class="empty-glyph">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/>
                        <circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/>
                        <line x1="8.5" y1="7.5" x2="15.5" y2="16.5"/>
                    </svg>
                </div>
                <h3>No connections yet</h3>
                <p>Link memories together to see the graph come alive.</p>
            </div>
        </div>

        <div v-else class="fade-in">
            <div class="page-header">
                <h1>Memory Graph</h1>
                <p>{{ nodes.length }} connected memories, {{ edges.length }} links</p>
            </div>

            <div class="graph-container" id="graph-container">
                <div class="graph-tooltip" id="graph-tooltip"></div>
                <svg id="graph-svg"></svg>
            </div>

            <div class="graph-legend">
                <span class="legend-item" style="font-weight:600;">Node types:</span>
                <span v-for="t in typeLegend" :key="t.type" class="legend-item">
                    <span class="legend-dot" :style="{ background: t.color }"></span>
                    {{ t.type }}
                </span>
                <span style="width:16px;"></span>
                <span class="legend-item" style="font-weight:600;">Link types:</span>
                <span v-for="l in linkLegend" :key="l.type" class="legend-item">
                    <span class="legend-dot" :style="{ background: l.color, borderRadius: '2px', width: '16px', height: '4px' }"></span>
                    {{ l.type }}
                </span>
            </div>
        </div>
    `,
});
