/* ============================================================
   Megregore — Beliefs Page (Vue Component)
   Philosophical belief tracking with D3.js graph visualization.
   ============================================================ */

megregoreApp.component('beliefs-page', {
    setup() {
        const activeTab = ref('map');
        const loading = ref(true);
        const error = ref('');
        const beliefs = ref([]);
        const tensions = ref([]);
        const domains = ref([]);
        const graphData = ref({ nodes: [], edges: [] });
        const selectedBelief = ref(null);
        const beliefDetail = ref(null);
        const expandedBeliefs = reactive(new Set());

        const domainFilter = ref('');
        const statusFilter = ref('');
        const minConfidence = ref(0);
        const graphContainer = ref(null);

        let svg = null;
        let simulation = null;

        const domainColors = {
            consciousness: '#a78bfa',
            metaphysics: '#60a5fa',
            quantum: '#22d3ee',
            epistemology: '#fbbf24',
            ethics: '#34d399',
            identity: '#f472b6',
            simulation: '#7c5bf5',
            general: '#6b7280',
        };

        const tensionColors = {
            contradiction: '#ef4444',
            tension: '#f59e0b',
            dependency: '#3b82f6',
            refinement: '#22c55e',
        };

        const tensionDash = {
            contradiction: '6,4',
            tension: '0',
            dependency: '0',
            refinement: '0',
        };

        const getDomainColor = (domain) => domainColors[domain] || domainColors.general;

        const loadData = async () => {
            loading.value = true;
            error.value = '';
            try {
                const [domainRes, beliefRes, tensionRes, graphRes] = await Promise.all([
                    App.api('/beliefs/domains'),
                    App.api('/beliefs', buildBeliefParams()),
                    App.api('/beliefs/tensions'),
                    App.api('/beliefs/graph'),
                ]);
                domains.value = domainRes || [];
                beliefs.value = beliefRes.beliefs || [];
                tensions.value = tensionRes || [];
                graphData.value = graphRes || { nodes: [], edges: [] };
            } catch (e) {
                error.value = e.message;
            } finally {
                loading.value = false;
            }
        };

        const buildBeliefParams = () => {
            const params = { limit: 100 };
            if (domainFilter.value) params.domain = domainFilter.value;
            if (statusFilter.value) params.status = statusFilter.value;
            if (minConfidence.value > 0) params.min_confidence = (minConfidence.value / 100).toFixed(2);
            return params;
        };

        const reloadBeliefs = async () => {
            try {
                const res = await App.api('/beliefs', buildBeliefParams());
                beliefs.value = res.beliefs || [];
            } catch (e) { /* ignore filter errors */ }
        };

        const fetchBeliefDetail = async (id) => {
            try {
                beliefDetail.value = await App.api(`/beliefs/${id}`);
                selectedBelief.value = id;
            } catch (e) {
                console.error('Failed to load belief detail:', e);
            }
        };

        const toggleBelief = async (belief) => {
            if (expandedBeliefs.has(belief.id)) {
                expandedBeliefs.delete(belief.id);
                return;
            }
            if (!belief._args) {
                try {
                    const res = await App.api(`/beliefs/${belief.id}`);
                    belief._args = res.arguments || [];
                } catch (e) {
                    belief._args = [];
                }
            }
            expandedBeliefs.add(belief.id);
        };

        const isExpanded = (id) => expandedBeliefs.has(id);

        const confPct = (v) => Math.round((v || 0) * 100) + '%';

        // --- D3 Graph ---

        const initGraph = () => {
            if (!graphContainer.value || typeof d3 === 'undefined') return;
            const container = graphContainer.value;
            const width = container.clientWidth || 600;
            const height = 500;

            d3.select(container).selectAll('*').remove();
            svg = d3.select(container)
                .append('svg')
                .attr('width', width)
                .attr('height', height);

            renderGraph(width, height);
        };

        const renderGraph = (width, height) => {
            if (!svg || !graphData.value.nodes.length) return;

            svg.selectAll('g.graph-layer').remove();
            const g = svg.append('g').attr('class', 'graph-layer');

            // Zoom
            svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', (e) => {
                g.attr('transform', e.transform);
            }));

            const nodes = graphData.value.nodes.map(n => ({
                ...n,
                radius: 8 + n.confidence * 16,
            }));

            const nodeMap = new Map(nodes.map(n => [n.id, n]));
            const links = graphData.value.edges
                .filter(e => nodeMap.has(e.source) && nodeMap.has(e.target))
                .map(e => ({ ...e }));

            simulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(links).id(d => d.id).distance(120))
                .force('charge', d3.forceManyBody().strength(-250))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(d => d.radius + 8));

            const link = g.append('g').selectAll('line')
                .data(links).join('line')
                .attr('stroke', d => tensionColors[d.tension_type] || '#999')
                .attr('stroke-width', d => 1 + d.severity * 3)
                .attr('stroke-dasharray', d => tensionDash[d.tension_type] || '0')
                .attr('opacity', 0.6);

            const node = g.append('g').selectAll('g')
                .data(nodes).join('g')
                .attr('cursor', 'pointer')
                .call(d3.drag()
                    .on('start', (e, d) => {
                        if (!e.active) simulation.alphaTarget(0.3).restart();
                        d.fx = d.x; d.fy = d.y;
                    })
                    .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
                    .on('end', (e, d) => {
                        if (!e.active) simulation.alphaTarget(0);
                        d.fx = null; d.fy = null;
                    }));

            node.append('circle')
                .attr('r', d => d.radius)
                .attr('fill', d => getDomainColor(d.domain))
                .attr('stroke', 'var(--bg-primary)')
                .attr('stroke-width', 2)
                .attr('opacity', 0.85);

            node.append('text')
                .text(d => d.content.length > 20 ? d.content.slice(0, 18) + '..' : d.content)
                .attr('text-anchor', 'middle')
                .attr('dy', d => d.radius + 14)
                .attr('fill', 'var(--text-secondary)')
                .attr('font-size', '10px');

            node.append('title').text(d => d.content);

            node.on('click', (e, d) => {
                e.stopPropagation();
                fetchBeliefDetail(d.id);
            });

            svg.on('click', () => {
                selectedBelief.value = null;
                beliefDetail.value = null;
            });

            simulation.on('tick', () => {
                link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
                node.attr('transform', d => `translate(${d.x},${d.y})`);
            });
        };

        const handleResize = () => {
            if (activeTab.value === 'map') initGraph();
        };

        onMounted(() => {
            loadData();
            window.addEventListener('resize', handleResize);
        });

        onUnmounted(() => {
            window.removeEventListener('resize', handleResize);
            if (simulation) simulation.stop();
        });

        watch(activeTab, (tab) => {
            if (tab === 'map') nextTick(() => initGraph());
        });

        watch([domainFilter, statusFilter, minConfidence], () => { reloadBeliefs(); });

        watch(graphData, () => {
            if (activeTab.value === 'map') nextTick(() => initGraph());
        }, { deep: true });

        return {
            activeTab, loading, error, beliefs, tensions, domains, graphData,
            selectedBelief, beliefDetail, domainFilter, statusFilter, minConfidence,
            graphContainer, toggleBelief, isExpanded, fetchBeliefDetail,
            getDomainColor, confPct,
            tensionColors, App,
        };
    },
    template: `
<div class="fade-in">
    <div class="page-header">
        <h1>Beliefs</h1>
    </div>

    <!-- Tabs -->
    <div style="display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:1.5rem;">
        <button v-for="tab in [{id:'map',label:'Belief Map'},{id:'list',label:'Belief List'},{id:'tensions',label:'Tensions'}]"
            :key="tab.id" @click="activeTab=tab.id"
            style="padding:0.6rem 1.2rem;background:none;border:none;cursor:pointer;font-size:0.95rem;position:relative;"
            :style="{color:activeTab===tab.id?'var(--primary)':'var(--text-secondary)',borderBottom:activeTab===tab.id?'2px solid var(--primary)':'2px solid transparent',fontWeight:activeTab===tab.id?600:400}">
            {{ tab.label }}
        </button>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div></div>
    <div v-else-if="error" class="empty-state fade-in"><h3>Something went wrong</h3><p>{{ error }}</p></div>

    <div v-else>
        <!-- Filters (shared) -->
        <div class="card" style="margin-bottom:1.5rem;padding:0.75rem 1rem;" v-if="activeTab!=='tensions'">
            <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
                <select v-model="domainFilter" style="padding:0.4rem 0.6rem;background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:0.875rem;">
                    <option value="">All Domains</option>
                    <option v-for="d in domains" :key="d.domain" :value="d.domain">{{ d.domain }} ({{ d.count }})</option>
                </select>
                <select v-model="statusFilter" style="padding:0.4rem 0.6rem;background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:0.875rem;">
                    <option value="">All Statuses</option>
                    <option value="active">Active</option>
                    <option value="revised">Revised</option>
                    <option value="abandoned">Abandoned</option>
                    <option value="exploring">Exploring</option>
                </select>
                <div style="display:flex;align-items:center;gap:0.5rem;font-size:0.875rem;">
                    <span style="color:var(--text-secondary);">Min Confidence:</span>
                    <input type="range" v-model.number="minConfidence" min="0" max="100" style="width:120px;">
                    <span>{{ minConfidence }}%</span>
                </div>
            </div>
        </div>

        <!-- Tab 1: Belief Map -->
        <div v-show="activeTab==='map'" style="display:flex;gap:1.5rem;">
            <div class="card" style="flex:1;min-height:520px;position:relative;padding:0;">
                <div ref="graphContainer" style="width:100%;height:500px;"></div>
                <div v-if="graphData.nodes.length===0" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);"
                    v-html="App.emptyState('No Beliefs Yet','Record beliefs via Echo to see the graph')"></div>
                <!-- Legend -->
                <div v-if="graphData.nodes.length>0" style="position:absolute;bottom:12px;left:12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:11px;opacity:0.9;">
                    <div style="margin-bottom:4px;font-weight:600;color:var(--text-secondary);">Tension Types</div>
                    <div v-for="(color, type) in tensionColors" :key="type" style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
                        <span :style="{width:'16px',height:'3px',background:color,display:'inline-block',borderRadius:'2px'}"></span>
                        <span style="color:var(--text-secondary);text-transform:capitalize;">{{ type }}</span>
                    </div>
                </div>
            </div>
            <!-- Detail Sidebar -->
            <div v-if="selectedBelief && beliefDetail" class="card" style="width:340px;max-height:520px;overflow-y:auto;">
                <div style="padding:1rem;">
                    <div style="display:flex;gap:0.5rem;margin-bottom:0.75rem;flex-wrap:wrap;">
                        <span class="type-badge" :style="{background:getDomainColor(beliefDetail.belief.domain)+'22',color:getDomainColor(beliefDetail.belief.domain),border:'1px solid '+getDomainColor(beliefDetail.belief.domain)+'44'}">{{ beliefDetail.belief.domain }}</span>
                        <span class="type-badge">{{ beliefDetail.belief.status }}</span>
                    </div>
                    <p style="line-height:1.6;margin-bottom:1rem;font-size:0.95rem;">{{ beliefDetail.belief.content }}</p>
                    <div style="margin-bottom:1rem;">
                        <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px;color:var(--text-secondary);">
                            <span>Confidence</span><span>{{ confPct(beliefDetail.belief.confidence) }}</span>
                        </div>
                        <div style="background:var(--bg-secondary);height:6px;border-radius:3px;overflow:hidden;">
                            <div :style="{width:confPct(beliefDetail.belief.confidence),background:getDomainColor(beliefDetail.belief.domain),height:'100%',borderRadius:'3px',transition:'width 0.3s'}"></div>
                        </div>
                    </div>
                    <div v-if="beliefDetail.arguments && beliefDetail.arguments.length">
                        <h4 style="font-size:0.85rem;margin:1rem 0 0.5rem;color:var(--text-secondary);">Arguments ({{ beliefDetail.arguments.length }})</h4>
                        <div v-for="arg in beliefDetail.arguments" :key="arg.id"
                            style="padding:0.5rem 0.6rem;background:var(--bg-secondary);border-radius:4px;margin-bottom:0.4rem;font-size:0.85rem;border-left:3px solid;"
                            :style="{borderLeftColor:arg.argument_type==='supporting'?'#22c55e':arg.argument_type==='counter'?'#ef4444':'#f59e0b'}">
                            <div style="font-size:0.75rem;font-weight:600;margin-bottom:2px;text-transform:capitalize;"
                                :style="{color:arg.argument_type==='supporting'?'#22c55e':arg.argument_type==='counter'?'#ef4444':'#f59e0b'}">{{ arg.argument_type }}</div>
                            {{ arg.content }}
                        </div>
                    </div>
                    <div v-if="beliefDetail.tensions && beliefDetail.tensions.length">
                        <h4 style="font-size:0.85rem;margin:1rem 0 0.5rem;color:var(--text-secondary);">Tensions ({{ beliefDetail.tensions.length }})</h4>
                        <div v-for="t in beliefDetail.tensions" :key="t.id"
                            style="padding:0.5rem 0.6rem;background:var(--bg-secondary);border-radius:4px;margin-bottom:0.4rem;font-size:0.85rem;">
                            <span class="type-badge" style="font-size:0.7rem;"
                                :style="{background:tensionColors[t.tension_type]+'22',color:tensionColors[t.tension_type]}">{{ t.tension_type }}</span>
                            <div style="margin-top:4px;color:var(--text-secondary);">{{ App.truncateText(t.description, 80) }}</div>
                        </div>
                    </div>
                    <div v-if="beliefDetail.linked_memories && beliefDetail.linked_memories.length">
                        <h4 style="font-size:0.85rem;margin:1rem 0 0.5rem;color:var(--text-secondary);">Linked Memories ({{ beliefDetail.linked_memories.length }})</h4>
                        <div v-for="m in beliefDetail.linked_memories" :key="m.id"
                            style="padding:0.5rem 0.6rem;background:var(--bg-secondary);border-radius:4px;margin-bottom:0.4rem;font-size:0.85rem;">
                            <span class="type-badge" style="font-size:0.7rem;">{{ m.link_type }}</span>
                            <div style="margin-top:4px;">{{ App.truncateText(m.memory_content, 80) }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab 2: Belief List -->
        <div v-show="activeTab==='list'">
            <div v-if="beliefs.length===0" v-html="App.emptyState('No Beliefs Found','Adjust filters or record beliefs via Echo')"></div>
            <div v-else style="display:grid;gap:0.75rem;">
                <div v-for="b in beliefs" :key="b.id" class="card" style="overflow:hidden;">
                    <div @click="toggleBelief(b)" style="padding:0.75rem 1rem;display:flex;justify-content:space-between;align-items:center;cursor:pointer;">
                        <div style="display:flex;align-items:center;gap:0.75rem;flex:1;min-width:0;">
                            <span class="type-badge" :style="{background:getDomainColor(b.domain)+'22',color:getDomainColor(b.domain),border:'1px solid '+getDomainColor(b.domain)+'44',fontSize:'0.75rem'}">{{ b.domain }}</span>
                            <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ b.content }}</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:1rem;flex-shrink:0;margin-left:1rem;">
                            <div style="width:80px;">
                                <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--text-secondary);margin-bottom:2px;">
                                    <span>Conf</span><span>{{ confPct(b.confidence) }}</span>
                                </div>
                                <div style="background:var(--bg-secondary);height:4px;border-radius:2px;overflow:hidden;">
                                    <div :style="{width:confPct(b.confidence),background:getDomainColor(b.domain),height:'100%'}"></div>
                                </div>
                            </div>
                            <span class="type-badge" style="font-size:0.7rem;">{{ b.status }}</span>
                            <span style="font-size:0.8rem;color:var(--text-secondary);white-space:nowrap;">{{ b.argument_count || 0 }} args</span>
                            <span style="transition:transform 0.2s;font-size:0.7rem;" :style="{transform:isExpanded(b.id)?'rotate(180deg)':''}">&#9660;</span>
                        </div>
                    </div>
                    <div v-if="isExpanded(b.id)" style="padding:0.75rem 1rem;border-top:1px solid var(--border);background:var(--bg-surface);">
                        <p style="line-height:1.6;margin-bottom:0.75rem;">{{ b.content }}</p>
                        <div v-if="b.source_context" style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:0.75rem;">
                            <strong>Context:</strong> {{ b.source_context }}
                        </div>
                        <div v-if="b._args && b._args.length">
                            <h4 style="font-size:0.85rem;margin-bottom:0.5rem;color:var(--text-secondary);">Arguments</h4>
                            <div v-for="arg in b._args" :key="arg.id"
                                style="padding:0.5rem 0.6rem;background:var(--bg-primary);border-radius:4px;margin-bottom:0.4rem;font-size:0.85rem;border-left:3px solid;"
                                :style="{borderLeftColor:arg.argument_type==='supporting'?'#22c55e':arg.argument_type==='counter'?'#ef4444':'#f59e0b'}">
                                <div style="font-size:0.75rem;font-weight:600;text-transform:capitalize;"
                                    :style="{color:arg.argument_type==='supporting'?'#22c55e':arg.argument_type==='counter'?'#ef4444':'#f59e0b'}">{{ arg.argument_type }} ({{ (arg.strength * 100).toFixed(0) }}%)</div>
                                {{ arg.content }}
                            </div>
                        </div>
                        <div v-else style="color:var(--text-muted);font-size:0.85rem;">No arguments recorded</div>
                        <div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.5rem;">Created {{ App.formatDate(b.created_at) }}</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab 3: Tensions -->
        <div v-show="activeTab==='tensions'">
            <div class="table-container">
                <table v-if="tensions.length" class="data-table">
                    <thead>
                        <tr>
                            <th>Belief A</th>
                            <th>Belief B</th>
                            <th>Type</th>
                            <th>Severity</th>
                            <th>Status</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="t in [...tensions].sort((a,b) => b.severity - a.severity)" :key="t.id">
                            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="t.belief_a_content">{{ App.truncateText(t.belief_a_content, 50) }}</td>
                            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="t.belief_b_content">{{ App.truncateText(t.belief_b_content, 50) }}</td>
                            <td>
                                <span class="type-badge" :style="{background:(tensionColors[t.tension_type]||'#999')+'22',color:tensionColors[t.tension_type]||'#999'}">{{ t.tension_type }}</span>
                            </td>
                            <td>
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <div style="background:var(--bg-secondary);height:5px;border-radius:3px;overflow:hidden;width:50px;">
                                        <div :style="{width:(t.severity*100)+'%',background:tensionColors[t.tension_type]||'#999',height:'100%'}"></div>
                                    </div>
                                    <span style="font-size:0.8rem;color:var(--text-secondary);">{{ (t.severity*100).toFixed(0) }}%</span>
                                </div>
                            </td>
                            <td><span class="type-badge" style="font-size:0.7rem;">{{ t.status }}</span></td>
                            <td style="max-width:200px;color:var(--text-secondary);font-size:0.85rem;">{{ App.truncateText(t.description, 60) }}</td>
                        </tr>
                    </tbody>
                </table>
                <div v-else v-html="App.emptyState('No Tensions','No belief tensions recorded yet')"></div>
            </div>
        </div>
    </div>
</div>
    `
});
