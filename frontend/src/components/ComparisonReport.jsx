import { ChevronDown, ChevronUp, Copy, Download } from 'lucide-react';
import {ResponsiveContainer, BarChart, XAxis, YAxis, Tooltip, Legend, Bar, PieChart, Pie, Cell} from 'recharts';
import { useState } from 'react';
import './ComparisonReport.css';

export default function ComparisonReport({ reports = [] }) {
  const [expandedMetrics, setExpandedMetrics] = useState({});

  if (!reports || reports.length === 0) {
    return (
      <div className="comparison-report">
        <p className="no-data">Run workflows to generate comparison data</p>
      </div>
    );
  }

  const toggleMetric = (metricKey) => {
    setExpandedMetrics((prev) => ({
      ...prev,
      [metricKey]: !prev[metricKey],
    }));
  };

  const downloadJSON = () => {
    const json = JSON.stringify(reports, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `workflow-comparison-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    const json = JSON.stringify(reports, null, 2);
    navigator.clipboard.writeText(json);
  };

  const workflows = reports;

  const runtimeData = workflows.map(wf => ({
    name: wf.workflowName,
    runtime: +(wf.stats.runtimeMs / 1000).toFixed(2)
  }));

  const executionData = workflows.map(wf => ({
    name: wf.workflowName,
    agents: wf.stats.agentCalls,
    tools: wf.stats.toolCalls,
    retrievers: wf.stats.retrieverCalls
  }));

  const tokenData = workflows.map(wf => {
    let input = 0;
    let output = 0;

    Object.values(wf.stats.tokens).forEach(t => {
      input += t.inputTokens;
      output += t.outputTokens;
    });

    return {
      name: wf.workflowName,
      tokens: [
        {
          name: "Input Tokens",
          value: input
        },
        {
          name: "Output Tokens",
          value: output
        }
      ]
    };
  });
  const agentDurationData = [];
  const agents = new Set();

  workflows.forEach(wf=>{
    Object.keys(wf.stats.durations)
      .forEach(a=>agents.add(a));
  });

  agents.forEach(agent=>{
    let row={
      agent
    };
    workflows.forEach(wf=>{
      row[wf.workflowName] =
        wf.stats.durations[agent]
          ? +(wf.stats.durations[agent]/1e9).toFixed(2)
          : 0;
    });
    agentDurationData.push(row);
  });

  const chartColors=[
  "#112d33",
  "#305d70",
  "#facc15",
  "#f472b6",
  "#a78bfa"
  ];

  return (
    <div className="comparison-report">
      <div className="report-header">
        <div className="report-actions">
          <button onClick={copyToClipboard} title="Copy to clipboard">
            <Copy size={14} />
          </button>
          <button onClick={downloadJSON} title="Download as JSON">
            <Download size={14} />
          </button>
        </div>
      </div>

      <div className="comparison-grid">

        {/* Performance Metrics */}
        <div className="workflow-comparison">
          {reports.map((report, index) => (
            <div class="workflow-card" key={index}>
              <div class="header">
                <h2>Workflow {index + 1}</h2>
                <span className={`status-badge ${report.status}`}>
                  {report.status.toUpperCase()}
                </span>
              </div>
              

              <div class="stats-grid">
                <div class="stat">
                  <span class="label">Runtime</span>
                  <span class="value">{report.stats.runtimeMs.toFixed(0)} ms</span>
                </div>

                <div class="stat">
                  <span class="label">Nodes Executed</span>
                  <span class="value">{report.stats.nodesExecuted}</span>
                </div>

                <div class="stat">
                  <span class="label">Agent Calls</span>
                  <span class="value">{report.stats.agentCalls}</span>
                </div>

                <div class="stat">
                  <span class="label">Sub-Agent Calls</span>
                  <span class="value">{report.stats.subAgentCalls}</span>
                </div>

                <div class="stat">
                  <span class="label">Tool Calls</span>
                  <span class="value">{report.stats.toolCalls}</span>
                </div>

                <div class="stat">
                  <span class="label">Retriever Calls</span>
                  <span class="value">{report.stats.retrieverCalls}</span>
                </div>

                <div class="stat">
                  <span class="label">Input Tokens</span>
                  <span class="value">{Object.values(report.stats?.tokens ?? {}).reduce((sum, agent) => sum + agent.inputTokens, 0)}</span>
                </div>

                <div class="stat">
                  <span class="label">Output Tokens</span>
                  <span class="value">{Object.values(report.stats?.tokens ?? {}).reduce((sum, agent) => sum + agent.outputTokens, 0)}</span>
                </div>
              </div>

              <h3>Agent Durations</h3>

              <div class="agent-list">
                {Object.entries(report.stats.durations).map(([agent, duration]) => (
                  <div class="agent-row" key={agent}>
                    <span>{report.nodeResults[agent].label}</span>
                    <span>{(duration / 1e9).toFixed(2)} s</span>
                  </div>
                ))}
              </div>

              <h3>Token Usage</h3>

              <div class="agent-list">
                {Object.entries(report.stats.tokens).map(([agent, token]) => (
                  <div class="agent-row" key={agent}>
                    <span>{report.nodeResults[agent].label}</span>
                    <span>
                      In: {token.inputTokens} | Out: {token.outputTokens}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Output Comparison */}
        <div className="comparison-section">
          <div className="metric-content">
            <div className="workflow-comparison">
              {reports.map((report, index) => (
                <div className="workflow-card" key={index}>
                  <h2>{report.workflowName}</h2>

                  <div className="output-card">
                    {report.output ? (
                      <pre>{report.output}</pre>
                    ) : (
                      <em>No output</em>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Logs & Events */}
        <div className="metric-content logs-grid">
          {reports.map((report, idx) => (
            <div key={idx} className="log-section">
              <div className="log-header">
                <h5>{report.workflowName}</h5>
              </div>

              <div className="log-list">
                {(report.logs || []).length > 0 ? (
                  (report.logs || []).slice(0, 5).map((log, logIdx) => (
                    <div key={logIdx} className="log-entry">
                      <span className={`log-level ${log.level || 'info'}`}>
                        {(log.level || 'INFO').toUpperCase()}
                      </span>

                      <span className="log-text">
                        {truncate(log.message || '', 100)}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="no-logs">
                    <em>No logs</em>
                  </div>
                )}

                {(report.logs || []).length > 5 && (
                  <div className="log-more">
                    +{(report.logs || []).length - 5} more logs
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="comparison-section charts-section">
          <div className="charts-grid">

            {/* Runtime */}
            <div className="chart-card">
              <h3>Runtime Comparison</h3>

              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={runtimeData}>
                  <XAxis 
                    dataKey="name"
                    stroke="#9aa7bd"
                  />

                  <YAxis 
                    stroke="#9aa7bd"
                  />

                  <Tooltip cursor= {{fill: "#9aa7bd"}}/>

                  <Bar 
                    dataKey="runtime"
                    fill="rgba(6, 95, 70, 0.24)"
                    stroke="#35d49a"
                    radius={[6,6,0,0]}
                  />
                </BarChart>
              </ResponsiveContainer>

            </div>



            {/* Execution Metrics */}
            <div className="chart-card">

              <h3>Execution Metrics</h3>

              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={executionData}>

                  <XAxis 
                    dataKey="name"
                    stroke="#9aa7bd"
                  />

                  <YAxis 
                    stroke="#9aa7bd"
                  />

                  <Tooltip cursor= {{fill: "#9aa7bd"}}/>

                  <Legend />
                  <Bar 
                    dataKey="agents"
                    name="Agents"
                    fill="rgba(73, 214, 255, 0.32)"
                    stroke="#4db3d4"
                  />

                  <Bar 
                    dataKey="tools"
                    name="Tools"
                    fill="#313030"
                    stroke="#dfb357"
                  />

                  <Bar 
                    dataKey="retrievers"
                    name="Retrievers"
                    fill="#322542"
                    stroke="#e471c2"
                  />

                </BarChart>
              </ResponsiveContainer>

            </div>




            {/* Token Usage */}
            <div className="chart-card">
              <h3>Token Usage</h3>
              <div className="pie-container">
                {tokenData.map((workflow, index) => (
                  <div key={workflow.name} className="workflow-pie">
                    <h2>{workflow.name}</h2>

                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={workflow.tokens}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          outerRadius={70}
                          label
                        >
                          <Cell fill="#305d70" />
                          <Cell fill="#664b87" />
                        </Pie>

                        <Tooltip
                          formatter={(value) => `${value} tokens`}
                          cursor= {{fill: "#9aa7bd"}}
                        />

                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                ))}
              </div>
            </div>




            {/* Agent Duration */}
            <div className="chart-card">

              <h3>Agent Duration</h3>


              <ResponsiveContainer width="100%" height={250}>

                <BarChart data={agentDurationData}>

                  <XAxis
                    dataKey="agent"
                    stroke="#9aa7bd"
                  />

                  <YAxis
                    stroke="#9aa7bd"
                    unit="s"
                  />

                  <Tooltip cursor= {{fill: "#9aa7bd"}}/>

                  <Legend />

                  {
                    workflows.map((wf,index)=>(
                      <Bar
                        key={wf.workflowId}
                        dataKey={wf.workflowName}
                        fill={
                          chartColors[index % chartColors.length]
                        }
                        stroke="#8e9bae52"
                      />
                    ))
                  }

                </BarChart>

              </ResponsiveContainer>

            </div>


          </div>

        </div>
      </div>
    </div>
  );
}

function formatDuration(ms) {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function truncate(text, length) {
  if (!text) return '';
  return text.length > length ? text.substring(0, length) + '...' : text;
}
