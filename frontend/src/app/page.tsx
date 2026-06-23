'use client';

import React, { useState, useEffect, useRef } from 'react';

// API Configuration
const API_BASE_URL = 'http://localhost:8001/api';

// Interface Definitions
interface Stock {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  total_assets: number;
  total_debt: number;
  cash_equivalents: number;
  accounts_receivable: number;
  total_revenue: number;
  interest_income: number;
  shares_outstanding: number;
  avg_market_cap_36mo: number;
  grade?: string;
  compliance_score?: number;
  debt_ratio?: number;
  cash_ratio?: number;
  tangibility_ratio?: number;
  total_haram_ratio?: number;
  purification_per_share?: number;
  halal_failure?: string;
}

interface Rule {
  ticker?: string;
  pattern?: string;
  segment_name?: string;
  compliance_status: string;
  notes: string;
}

interface OptimizeResult {
  weights: Record<string, number>;
  expected_return: number;
  volatility: number;
  purification_per_1000: number;
  allocation: Record<string, number>;
  sector_exposure: Record<string, number>;
  prices: Record<string, number>;
  purification_map: Record<string, number>;
}

interface BacktestResult {
  portfolio_return: number;
  spy_return: number;
  outperformance: number;
  sharpe: number;
}

interface LiveQuote {
  ticker: string;
  live_price: number;
  live_market_cap: number;
  live_grade: string;
  live_score: number;
  debt_ratio: number;
  cash_ratio: number;
  tangibility_ratio: number;
  interest_income_ratio: number;
  haram_revenue_ratio: number;
  total_haram_ratio: number;
  doubtful_revenue_ratio: number;
  total_combined_ratio: number;
  pass_sector: boolean;
  pass_industry: boolean;
  pass_debt: boolean;
  pass_cash: boolean;
  pass_tangibility: boolean;
  pass_interest: boolean;
  pass_combined: boolean;
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<'halal' | 'doubtful' | 'rejected' | 'optimizer' | 'backtest' | 'explorer' | 'rules' | 'mcp' | 'overrides'>('halal');
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>('');

  // Pipeline Status Indicators
  const [ingesting, setIngesting] = useState<boolean>(false);
  const [screening, setScreening] = useState<boolean>(false);

  // Form States
  const [manualTicker, setManualTicker] = useState<string>('');
  const [manualHaramRevenue, setManualHaramRevenue] = useState<string>('');
  const [manualDebtRatio, setManualDebtRatio] = useState<string>('');
  const [manualReason, setManualReason] = useState<string>('');

  // Optimizer Inputs & Outputs
  const [maxWeight, setMaxWeight] = useState<number>(0.10);
  const [sectorCap, setSectorCap] = useState<number>(0.30);
  const [strategy, setStrategy] = useState<string>('Max Sharpe');
  const [targetVol, setTargetVol] = useState<number>(15);
  const [targetRet, setTargetRet] = useState<number>(15);
  const [optimizeResult, setOptimizeResult] = useState<OptimizeResult | null>(null);
  const [optimizing, setOptimizing] = useState<boolean>(false);
  const [investAmount, setInvestAmount] = useState<number>(10000);
  const [sharesCalculator, setSharesCalculator] = useState<Record<string, number>>({});
  const [frontierChartUrl, setFrontierChartUrl] = useState<string>('');

  // Backtest States
  const [backtestWindow, setBacktestWindow] = useState<number>(12);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestRunning, setBacktestRunning] = useState<boolean>(false);
  const [backtestChartUrl, setBacktestChartUrl] = useState<string>('');

  // Stock Explorer States
  const [allTickers, setAllTickers] = useState<{ ticker: string; name: string; sector: string }[]>([]);
  const [selectedExplorerTicker, setSelectedExplorerTicker] = useState<string>('');
  const [explorerStockDetails, setExplorerStockDetails] = useState<any | null>(null);
  const [explorerLiveQuote, setExplorerLiveQuote] = useState<LiveQuote | null>(null);
  const [explorerLiveLoading, setExplorerLiveLoading] = useState<boolean>(false);
  const [explorerLiveError, setExplorerLiveError] = useState<string | null>(null);
  
  // Custom Ticker Ingestion
  const [customTicker, setCustomTicker] = useState<string>('');
  const [addingCustomTicker, setAddingCustomTicker] = useState<boolean>(false);
  const [customSecUrl, setCustomSecUrl] = useState<string>('');


  // AI Auditor States
  const [aiAuditing, setAiAuditing] = useState<boolean>(false);
  const [aiAuditStep, setAiAuditStep] = useState<string>('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Rules States
  const [tickerRules, setTickerRules] = useState<Rule[]>([]);
  const [globalRules, setGlobalRules] = useState<Rule[]>([]);
  const [rulesLoading, setRulesLoading] = useState<boolean>(false);

  // MCP States
  const [mcpStatus, setMcpStatus] = useState<any | null>(null);
  const [mcpLoading, setMcpLoading] = useState<boolean>(false);

  // Load list of all tickers on mount or when a pipeline completes
  const fetchAllTickers = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/stocks`);
      if (res.ok) {
        const data = await res.json();
        setAllTickers(data);
      }
    } catch (e) {
      console.error('Failed to load tickers', e);
    }
  };

  useEffect(() => {
    fetchAllTickers();
  }, []);

  // Fetch Universe Lists
  const fetchUniverse = async (universe: 'halal' | 'doubtful' | 'rejected') => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/universe/${universe}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      setStocks(data);
    } catch (err: any) {
      setError(`Failed to fetch stocks: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (['halal', 'doubtful', 'rejected'].includes(activeTab)) {
      fetchUniverse(activeTab as 'halal' | 'doubtful' | 'rejected');
    } else if (activeTab === 'rules') {
      fetchRules();
    } else if (activeTab === 'mcp') {
      fetchMcpStatus();
    }
  }, [activeTab]);

  // Fetch Active Shariah Segment Rules
  const fetchRules = async () => {
    setRulesLoading(true);
    try {
      const resTicker = await fetch(`${API_BASE_URL}/rules/ticker-rules`);
      const resGlobal = await fetch(`${API_BASE_URL}/rules/global-rules`);
      if (resTicker.ok && resGlobal.ok) {
        setTickerRules(await resTicker.json());
        setGlobalRules(await resGlobal.json());
      }
    } catch (err) {
      console.error('Failed to fetch rules', err);
    } finally {
      setRulesLoading(false);
    }
  };

  // Fetch SRE Agent status
  const fetchMcpStatus = async () => {
    setMcpLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/mcp/status`);
      if (res.ok) {
        setMcpStatus(await res.json());
      }
    } catch (err) {
      console.error('Failed to fetch SRE Agent status', err);
    } finally {
      setMcpLoading(false);
    }
  };

  // Run Ingestion
  const triggerIngestion = async () => {
    setIngesting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/pipeline/ingest?refresh=true`, { method: 'POST' });
      const data = await response.json();
      alert(data.message);
      fetchAllTickers();
    } catch (err: any) {
      alert(`Ingestion failed: ${err.message}`);
    } finally {
      setIngesting(false);
    }
  };

  // Run Screener
  const triggerScreening = async () => {
    setScreening(true);
    try {
      const response = await fetch(`${API_BASE_URL}/pipeline/screen`, { method: 'POST' });
      const data = await response.json();
      alert(data.message);
      if (['halal', 'doubtful', 'rejected'].includes(activeTab)) {
        fetchUniverse(activeTab as any);
      }
    } catch (err: any) {
      alert(`Screening failed: ${err.message}`);
    } finally {
      setScreening(false);
    }
  };

  // Submit Override
  const submitOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualTicker) return;

    try {
      const response = await fetch(`${API_BASE_URL}/overrides/manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: manualTicker,
          haram_revenue_override: manualHaramRevenue ? parseFloat(manualHaramRevenue) : null,
          debt_ratio_override: manualDebtRatio ? parseFloat(manualDebtRatio) : null,
          reasoning: manualReason
        })
      });
      if (response.ok) {
        alert(`Override saved for ${manualTicker.toUpperCase()}`);
        setManualTicker('');
        setManualHaramRevenue('');
        setManualDebtRatio('');
        setManualReason('');
        if (['halal', 'doubtful', 'rejected'].includes(activeTab)) {
          fetchUniverse(activeTab as any);
        }
      }
    } catch (err: any) {
      alert(`Override failed: ${err.message}`);
    }
  };

  // Run Optimizer
  const triggerOptimization = async () => {
    setOptimizing(true);
    setOptimizeResult(null);
    try {
      const response = await fetch(`${API_BASE_URL}/portfolio/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_weight: maxWeight,
          sector_cap: sectorCap,
          strategy: strategy,
          target_vol: targetVol / 100.0,
          target_ret: targetRet / 100.0
        })
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Constraints impossible to satisfy');
      }
      const data = await response.json();
      setOptimizeResult(data);
      
      // Initialize calculator values
      const calcShares: Record<string, number> = {};
      Object.entries(data.allocation as Record<string, number>).forEach(([ticker, w]) => {
        const price = data.prices[ticker] || 1.0;
        calcShares[ticker] = Number(((investAmount * w) / price).toFixed(4));
      });
      setSharesCalculator(calcShares);
      
      // Load Frontier chart
      setFrontierChartUrl(`${API_BASE_URL}/portfolio/frontier-chart?t=${Date.now()}`);
    } catch (err: any) {
      alert(`Optimization failed: ${err.message}`);
    } finally {
      setOptimizing(false);
    }
  };

  // Portfolio Calculator updates
  useEffect(() => {
    if (optimizeResult) {
      const calcShares: Record<string, number> = {};
      Object.entries(optimizeResult.allocation).forEach(([ticker, w]) => {
        const price = optimizeResult.prices[ticker] || 1.0;
        calcShares[ticker] = Number(((investAmount * w) / price).toFixed(4));
      });
      setSharesCalculator(calcShares);
    }
  }, [investAmount, optimizeResult]);

  const handleShareChange = (ticker: string, value: number) => {
    setSharesCalculator(prev => ({
      ...prev,
      [ticker]: value
    }));
  };

  const getPurificationTotal = () => {
    if (!optimizeResult) return 0;
    let sum = 0;
    Object.entries(sharesCalculator).forEach(([ticker, shares]) => {
      const pur = optimizeResult.purification_map[ticker] || 0;
      sum += shares * pur;
    });
    return sum;
  };

  // Run Performance Simulation
  const triggerBacktest = async () => {
    setBacktestRunning(true);
    setBacktestResult(null);
    try {
      const res = await fetch(`${API_BASE_URL}/portfolio/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ months: backtestWindow })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Backtest failed');
      }
      const data = await res.json();
      setBacktestResult(data);
      setBacktestChartUrl(`${API_BASE_URL}/portfolio/backtest-chart?t=${Date.now()}`);
    } catch (err: any) {
      alert(`Backtest failed: ${err.message}`);
    } finally {
      setBacktestRunning(false);
    }
  };

  // Ingest Custom Ticker
  const handleAddCustomTicker = async () => {
    if (!customTicker) return;
    setAddingCustomTicker(true);
    try {
      let url = `${API_BASE_URL}/stocks/${customTicker}/ingest`;
      if (customSecUrl.trim()) {
        url += `?sec_url=${encodeURIComponent(customSecUrl.trim())}`;
      }
      const res = await fetch(url, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        alert(data.message);
        setCustomTicker('');
        setCustomSecUrl('');
        fetchAllTickers();
      } else {
        alert(data.detail || 'Failed to ingest custom ticker');
      }
    } catch (err: any) {
      alert(`Ingest error: ${err.message}`);
    } finally {
      setAddingCustomTicker(false);
    }
  };


  // Delete Ticker
  const handleDeleteStock = async (ticker: string) => {
    if (!confirm(`Are you sure you want to permanently delete ${ticker} and its overrides from the database?`)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/stocks/${ticker}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok) {
        alert(data.message);
        setSelectedExplorerTicker('');
        setExplorerStockDetails(null);
        setExplorerLiveQuote(null);
        fetchAllTickers();
      } else {
        alert(data.detail || 'Failed to delete ticker');
      }
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`);
    }
  };

  // Stock Explorer: Load Stock Details
  useEffect(() => {
    if (!selectedExplorerTicker) {
      setExplorerStockDetails(null);
      setExplorerLiveQuote(null);
      return;
    }

    const loadDetails = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/stocks/${selectedExplorerTicker}`);
        if (res.ok) {
          const data = await res.json();
          setExplorerStockDetails(data);
        }
      } catch (err) {
        console.error('Failed to load stock details', err);
      }
    };

    loadDetails();
  }, [selectedExplorerTicker]);

  // Real-Time Compliance quote: Automatically fetches and updates at all times when a stock is selected!
  useEffect(() => {
    if (!selectedExplorerTicker) return;

    const fetchQuote = async () => {
      setExplorerLiveLoading(true);
      setExplorerLiveError(null);
      try {
        const res = await fetch(`${API_BASE_URL}/stocks/${selectedExplorerTicker}/quote`);
        if (!res.ok) throw new Error('Real-time price feed failed');
        const quote = await res.json();
        setExplorerLiveQuote(quote);
      } catch (err: any) {
        setExplorerLiveError(err.message);
      } finally {
        setExplorerLiveLoading(false);
      }
    };

    fetchQuote();

    // Regularly update quotes in background every 5 seconds (shows at all times, no toggle)
    const interval = setInterval(() => {
      fetchQuote();
    }, 5000);

    return () => clearInterval(interval);
  }, [selectedExplorerTicker]);

  // Run AI Audit on Stock
  const triggerAiAudit = async (type: 'standard' | 'source_backed' | 'multi_source') => {
    if (!selectedExplorerTicker) return;
    setAiAuditing(true);
    
    const steps: Record<string, string> = {
      standard: '🧠 Running standard Gemini compliance check...',
      source_backed: '🔍 Downloading annual 10-K from SEC EDGAR and executing AI Vector audit...',
      multi_source: '🌐 Harvesting SEC filings + Earnings transcripts and performing cross-source audit...'
    };
    setAiAuditStep(steps[type]);

    try {
      const res = await fetch(`${API_BASE_URL}/stocks/${selectedExplorerTicker}/audit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audit_type: type })
      });
      const data = await res.json();
      if (res.ok) {
        alert('AI Audit completed and saved successfully!');
        // Reload details to capture the override reasoning
        const resD = await fetch(`${API_BASE_URL}/stocks/${selectedExplorerTicker}`);
        if (resD.ok) setExplorerStockDetails(await resD.json());
      } else {
        alert(data.detail || 'AI Audit failed');
      }
    } catch (err: any) {
      alert(`AI Audit error: ${err.message}`);
    } finally {
      setAiAuditing(false);
      setAiAuditStep('');
    }
  };

  // Run Document Upload Audit
  const handleUploadAudit = async () => {
    if (!selectedExplorerTicker || !uploadFile) return;
    setAiAuditing(true);
    setAiAuditStep(`📤 Uploading and parsing ${uploadFile.name} using Shariah heuristics...`);

    const formData = new FormData();
    formData.append('file', uploadFile);

    try {
      const res = await fetch(`${API_BASE_URL}/stocks/${selectedExplorerTicker}/upload-audit`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        alert('Document AI audit complete!');
        setUploadFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
        // Reload details
        const resD = await fetch(`${API_BASE_URL}/stocks/${selectedExplorerTicker}`);
        if (resD.ok) setExplorerStockDetails(await resD.json());
      } else {
        alert(data.detail || 'Document upload audit failed');
      }
    } catch (err: any) {
      alert(`Upload error: ${err.message}`);
    } finally {
      setAiAuditing(false);
      setAiAuditStep('');
    }
  };

  // Helper: check parsing of override reasoning for AI verdict display
  const getAiVerdict = () => {
    if (!explorerStockDetails || !explorerStockDetails.override_reason) return null;
    try {
      const data = JSON.parse(explorerStockDetails.override_reason);
      if (typeof data === 'object') return data;
    } catch (e) {
      // Return as raw string
    }
    return { reasoning: explorerStockDetails.override_reason };
  };

  const aiVerdict = getAiVerdict();

  // Filter Search
  const filteredStocks = stocks.filter(s =>
    s.ticker.toLowerCase().includes(search.toLowerCase()) ||
    (s.name && s.name.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <main className="min-h-screen bg-mesh text-[#f1f5f9] p-6 lg:p-12">
      {/* Header Panel */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center border-b border-[#1e293b] pb-6 mb-8 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-2xl">🌙</span>
            <h1 className="text-2xl font-black tracking-tight text-[#f1f5f9] uppercase">
              Aegis Shariah compliant Screener
            </h1>
          </div>
          <p className="text-xs text-[#94a3b8] mt-1 tracking-wider uppercase font-semibold">
            AAOIFI Compliance Engine & Modern Portfolio Optimizer
          </p>
        </div>

        {/* Action controls */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={triggerIngestion}
            disabled={ingesting}
            className="bg-[#1e293b] hover:bg-[#334155] border border-[#334155] disabled:opacity-50 text-[#f1f5f9] px-4 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition cursor-pointer"
          >
            {ingesting ? 'Fetching Finance Data...' : '🔄 Fetch Latest Data'}
          </button>
          <button
            onClick={triggerScreening}
            disabled={screening}
            className="bg-[#f59e0b] hover:bg-[#d97706] disabled:opacity-50 text-[#090d16] px-4 py-2 rounded-lg text-xs font-black uppercase tracking-wider transition cursor-pointer"
          >
            {screening ? 'Screening Universe...' : '⚙️ Run screener'}
          </button>
        </div>
      </header>

      {/* Tabs Navigation */}
      <nav className="flex flex-wrap gap-2 border-b border-[#1e293b] pb-4 mb-8">
        {([
          { id: 'halal', label: '🟢 Halal Universe' },
          { id: 'doubtful', label: '🟡 Doubtful Universe' },
          { id: 'rejected', label: '🔴 Rejections' },
          { id: 'optimizer', label: '📈 MPT Optimizer' },
          { id: 'backtest', label: '⏳ Historical Backtest' },
          { id: 'explorer', label: '🔍 Stock Explorer' },
          { id: 'rules', label: '⚙️ Segment Rules' },
          { id: 'mcp', label: '🤖 SRE Health' },
          { id: 'overrides', label: '🛠️ Overrides Desk' }
        ] as const).map(tab => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
              setError(null);
            }}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition cursor-pointer ${
              activeTab === tab.id
                ? 'bg-[#f59e0b] text-[#090d16]'
                : 'bg-[#090d16]/40 border border-[#1e293b] text-[#94a3b8] hover:text-[#f1f5f9] hover:bg-[#1e293b]/50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Primary Section */}
      <section className="space-y-8">
        
        {/* Table View Tabs (Halal, Doubtful, Rejections) */}
        {['halal', 'doubtful', 'rejected'].includes(activeTab) && (
          <div className="bg-[#090d16]/40 border border-[#1e293b] rounded-xl p-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
              <h2 className="text-base font-bold uppercase tracking-wider text-[#f59e0b]">
                {activeTab === 'halal' && '🟢 Halal Compliance List'}
                {activeTab === 'doubtful' && '🟡 Doubtful Compliance List'}
                {activeTab === 'rejected' && '🔴 Compliance Breaches (Rejections)'}
              </h2>
              <div className="flex items-center gap-3 w-full sm:w-auto">
                <input
                  type="text"
                  placeholder="Search Ticker or Name..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="bg-[#090d16] border border-[#334155] rounded-lg px-4 py-2 text-xs w-full sm:w-64 focus:outline-none focus:border-[#f59e0b]"
                />
                <span className="text-xs text-[#94a3b8] whitespace-nowrap bg-[#1e293b] px-2.5 py-1 rounded-md">
                  {filteredStocks.length} Stocks
                </span>
              </div>
            </div>

            {loading ? (
              <div className="text-center py-12 text-xs text-[#94a3b8] animate-pulse">Querying Database...</div>
            ) : error ? (
              <div className="text-red-400 text-xs py-6">{error}</div>
            ) : filteredStocks.length === 0 ? (
              <div className="text-center py-12 text-xs text-[#94a3b8]">No tickers matching query.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#1e293b] text-[#94a3b8] uppercase font-bold tracking-wider">
                      <th className="py-3 px-4">Ticker</th>
                      <th className="py-3 px-4">Name</th>
                      <th className="py-3 px-4">Sector</th>
                      <th className="py-3 px-4">Debt / Cap</th>
                      <th className="py-3 px-4">Cash / Cap</th>
                      <th className="py-3 px-4">Haram Ratio</th>
                      <th className="py-3 px-4">Purification</th>
                      <th className="py-3 px-4">Score</th>
                      {activeTab === 'rejected' && <th className="py-3 px-4 text-red-400">Rejection Reason</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStocks.map((stock) => (
                      <tr key={stock.ticker} className="border-b border-[#1e293b] hover:bg-[#1e293b]/20 transition-colors">
                        <td className="py-3 px-4 font-bold text-[#f59e0b]">{stock.ticker}</td>
                        <td className="py-3 px-4 max-w-xs truncate font-medium">{stock.name || 'N/A'}</td>
                        <td className="py-3 px-4 text-[#94a3b8]">{stock.sector || 'N/A'}</td>
                        <td className="py-3 px-4">{(stock.debt_ratio ? (stock.debt_ratio * 100).toFixed(2) : '0.00')}%</td>
                        <td className="py-3 px-4">{(stock.cash_ratio ? (stock.cash_ratio * 100).toFixed(2) : '0.00')}%</td>
                        <td className="py-3 px-4">{(stock.total_haram_ratio ? (stock.total_haram_ratio * 100).toFixed(2) : '0.00')}%</td>
                        <td className="py-3 px-4 font-semibold text-[#10b981]">
                          {stock.purification_per_share ? `$${stock.purification_per_share.toFixed(4)}` : '$0.0000'}
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-black ${
                            stock.grade?.startsWith('A') ? 'bg-[#10b981]/25 text-[#10b981]' :
                            stock.grade?.startsWith('B') || stock.grade?.startsWith('C') ? 'bg-[#f59e0b]/25 text-[#f59e0b]' :
                            'bg-[#ef4444]/25 text-[#ef4444]'
                          }`}>
                            {stock.grade || 'F'} ({stock.compliance_score ? stock.compliance_score.toFixed(1) : '0.0'})
                          </span>
                        </td>
                        {activeTab === 'rejected' && (
                          <td className="py-3 px-4 text-red-300 font-medium max-w-xs truncate">{stock.halal_failure || 'Financial boundaries breached'}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Portfolio MPT Optimizer Tab */}
        {activeTab === 'optimizer' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left sidebar panel */}
            <div className="bg-[#090d16]/60 border border-[#1e293b] p-6 rounded-xl space-y-6">
              <h3 className="text-xs font-black tracking-wider uppercase border-b border-[#1e293b] pb-2 text-[#f59e0b]">
                Optimizer Settings
              </h3>
              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-2">Strategy</label>
                <select
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b] font-medium"
                >
                  <option value="Max Sharpe">Max Sharpe Ratio</option>
                  <option value="Min Volatility">Minimum Volatility</option>
                  <option value="Target Volatility">Target Volatility Limit</option>
                  <option value="Target Return">Target Return Requirement</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Max Weight per Stock: {(maxWeight * 100).toFixed(0)}%</label>
                <input
                  type="range" min="0.05" max="0.20" step="0.01"
                  value={maxWeight} onChange={(e) => setMaxWeight(parseFloat(e.target.value))}
                  className="w-full accent-[#f59e0b]"
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Max Weight per Sector: {(sectorCap * 100).toFixed(0)}%</label>
                <input
                  type="range" min="0.10" max="0.50" step="0.05"
                  value={sectorCap} onChange={(e) => setSectorCap(parseFloat(e.target.value))}
                  className="w-full accent-[#f59e0b]"
                />
              </div>

              {strategy === 'Target Volatility' && (
                <div>
                  <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Target Volatility: {targetVol}%</label>
                  <input
                    type="range" min="5" max="30" step="1"
                    value={targetVol} onChange={(e) => setTargetVol(parseInt(e.target.value))}
                    className="w-full accent-[#f59e0b]"
                  />
                </div>
              )}

              {strategy === 'Target Return' && (
                <div>
                  <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Target Expected Return: {targetRet}%</label>
                  <input
                    type="range" min="5" max="30" step="1"
                    value={targetRet} onChange={(e) => setTargetRet(parseInt(e.target.value))}
                    className="w-full accent-[#f59e0b]"
                  />
                </div>
              )}

              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-2">Initial Investment Amount ($)</label>
                <input
                  type="number"
                  min="1000"
                  step="1000"
                  value={investAmount}
                  onChange={(e) => setInvestAmount(Number(e.target.value))}
                  className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b]"
                />
              </div>

              <button
                onClick={triggerOptimization}
                disabled={optimizing}
                className="w-full bg-[#f59e0b] hover:bg-[#d97706] text-[#090d16] font-bold py-2.5 px-4 rounded-lg text-xs tracking-wider uppercase disabled:opacity-50 transition cursor-pointer"
              >
                {optimizing ? 'Calculating Frontier...' : '🚀 Optimize Portfolio'}
              </button>
            </div>

            {/* Right main panel */}
            <div className="lg:col-span-2 space-y-6">
              {!optimizeResult ? (
                <div className="h-full border border-dashed border-[#334155] rounded-xl flex items-center justify-center text-center p-12 text-xs text-[#94a3b8]">
                  Select constraints and click "Optimize Portfolio" to render weights, sector cap limits, and calculations.
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Stats summaries */}
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-[#090d16]/80 p-4 border border-[#1e293b] rounded-xl text-center">
                      <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Expected return</span>
                      <p className="text-lg font-black text-[#10b981] mt-1">{(optimizeResult.expected_return * 100).toFixed(2)}%</p>
                    </div>
                    <div className="bg-[#090d16]/80 p-4 border border-[#1e293b] rounded-xl text-center">
                      <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Annual Volatility</span>
                      <p className="text-lg font-black text-[#f59e0b] mt-1">{(optimizeResult.volatility * 100).toFixed(2)}%</p>
                    </div>
                    <div className="bg-[#090d16]/80 p-4 border border-[#1e293b] rounded-xl text-center">
                      <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Purification Total</span>
                      <p className="text-lg font-black text-blue-400 mt-1">
                        ${((optimizeResult.purification_per_1000 * investAmount) / 1000).toFixed(2)}
                      </p>
                    </div>
                  </div>

                  {/* Dual Grid layout for allocation vs sector chart */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Frontier chart */}
                    <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl">
                      <h4 className="text-xs font-bold uppercase text-[#f59e0b] mb-4 tracking-wider">📈 Efficient Frontier</h4>
                      {frontierChartUrl && (
                        <img src={frontierChartUrl} alt="Efficient Frontier" className="rounded-lg w-full h-auto border border-[#1e293b]" />
                      )}
                    </div>

                    {/* Sector Exposure */}
                    <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl">
                      <h4 className="text-xs font-bold uppercase text-[#f59e0b] mb-4 tracking-wider">🏢 Sector Exposure</h4>
                      <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
                        {Object.entries(optimizeResult.sector_exposure)
                          .sort(([_, a], [__, b]) => b - a)
                          .map(([sector, w]) => (
                            <div key={sector}>
                              <div className="flex justify-between text-[11px] mb-1 font-medium">
                                <span>{sector}</span>
                                <span>{(w * 100).toFixed(2)}%</span>
                              </div>
                              <div className="w-full bg-[#1e293b] h-1.5 rounded-full overflow-hidden">
                                <div className="bg-[#f59e0b] h-full" style={{ width: `${w * 100}%` }}></div>
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  </div>

                  {/* Allocation targets table */}
                  <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl">
                    <h4 className="text-xs font-bold uppercase text-[#f59e0b] mb-4 tracking-wider">💰 Target Allocation Summary</h4>
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-[#1e293b] text-[#94a3b8] uppercase font-bold">
                          <th className="py-2">Ticker</th>
                          <th className="py-2">Weight</th>
                          <th className="py-2">Dollar Amount</th>
                          <th className="py-2">Current Price</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(optimizeResult.allocation)
                          .filter(([_, w]) => w > 0.001)
                          .sort(([_, a], [__, b]) => b - a)
                          .map(([ticker, w]) => (
                            <tr key={ticker} className="border-b border-[#1e293b]/40">
                              <td className="py-2 font-bold text-[#f59e0b]">{ticker}</td>
                              <td className="py-2">{(w * 100).toFixed(2)}%</td>
                              <td className="py-2">${(w * investAmount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                              <td className="py-2">${(optimizeResult.prices[ticker] || 0).toFixed(2)}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Interactive Purification Calculator (Restored!) */}
                  <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl">
                    <h4 className="text-xs font-black uppercase text-[#f59e0b] mb-2 tracking-wider">
                      🧮 Interactive Portfolio Purification Calculator
                    </h4>
                    <p className="text-[11px] text-[#94a3b8] mb-4">
                      Review or edit the **Current Share Count** to match your actual holdings and recalculate compliance obligations.
                    </p>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-[#1e293b] text-[#94a3b8] uppercase font-bold">
                            <th className="py-2 px-3">Ticker</th>
                            <th className="py-2 px-3">Price</th>
                            <th className="py-2 px-3">Target Weight</th>
                            <th className="py-2 px-3 w-40">Current Share Count</th>
                            <th className="py-2 px-3">Purification / Share</th>
                            <th className="py-2 px-3 text-right">Purification Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(optimizeResult.allocation)
                            .filter(([_, w]) => w > 0.001)
                            .map(([ticker, w]) => {
                              const price = optimizeResult.prices[ticker] || 1.0;
                              const purVal = optimizeResult.purification_map[ticker] || 0.0;
                              const shares = sharesCalculator[ticker] || 0;
                              return (
                                <tr key={ticker} className="border-b border-[#1e293b]/40">
                                  <td className="py-2 px-3 font-bold text-[#f59e0b]">{ticker}</td>
                                  <td className="py-2 px-3">${price.toFixed(2)}</td>
                                  <td className="py-2 px-3">{(w * 100).toFixed(2)}%</td>
                                  <td className="py-2 px-3">
                                    <input
                                      type="number"
                                      step="0.0001"
                                      min="0"
                                      value={shares}
                                      onChange={(e) => handleShareChange(ticker, parseFloat(e.target.value) || 0)}
                                      className="bg-[#090d16] border border-[#334155] rounded px-2 py-0.5 text-xs w-full focus:outline-none focus:border-[#f59e0b]"
                                    />
                                  </td>
                                  <td className="py-2 px-3 text-[#94a3b8]">${purVal.toFixed(4)}</td>
                                  <td className="py-2 px-3 text-right font-semibold text-[#10b981]">${(shares * purVal).toFixed(4)}</td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>

                    {/* Calculated donation summary box */}
                    <div className="bg-[#10b981]/10 border border-[#10b981]/30 rounded-xl p-5 mt-6 text-center">
                      <span className="text-[10px] uppercase font-bold text-[#10b981]">Total Donation/Purification Obligation</span>
                      <h3 className="text-3xl font-black text-[#10b981] mt-1">${getPurificationTotal().toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</h3>
                      <p className="text-[11px] text-[#94a3b8] mt-2 max-w-lg mx-auto leading-relaxed">
                        Purification obligation is calculated as `Shares × Purification Per Share` for all holdings. Purified earnings should be donated to clean water, medical aid, housing, or other humanitarian causes of your choice.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Historical Backtester Simulation Tab */}
        {activeTab === 'backtest' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left controller */}
            <div className="bg-[#090d16]/60 border border-[#1e293b] p-6 rounded-xl space-y-6">
              <h3 className="text-xs font-black tracking-wider uppercase border-b border-[#1e293b] pb-2 text-[#f59e0b]">
                Backtester Settings
              </h3>
              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-2">Simulation Window</label>
                <select
                  value={backtestWindow}
                  onChange={(e) => setBacktestWindow(Number(e.target.value))}
                  className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b] font-medium"
                >
                  <option value={6}>6 Months</option>
                  <option value={12}>12 Months</option>
                  <option value={18}>18 Months</option>
                  <option value={24}>24 Months</option>
                </select>
              </div>

              <button
                onClick={triggerBacktest}
                disabled={backtestRunning}
                className="w-full bg-[#f59e0b] hover:bg-[#d97706] text-[#090d16] font-bold py-2.5 px-4 rounded-lg text-xs tracking-wider uppercase disabled:opacity-50 transition cursor-pointer"
              >
                {backtestRunning ? 'Running Backtest...' : '🚀 Run Simulation'}
              </button>
            </div>

            {/* Right main visualization */}
            <div className="lg:col-span-2 space-y-6">
              {!backtestResult ? (
                <div className="h-full border border-dashed border-[#334155] rounded-xl flex items-center justify-center text-center p-12 text-xs text-[#94a3b8]">
                  Click "Run Simulation" to execute the backtest over the selected window.
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Metric panels */}
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-[#090d16]/80 p-4 border border-[#1e293b] rounded-xl text-center">
                      <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Portfolio Return</span>
                      <p className="text-xl font-black text-[#10b981] mt-1">{(backtestResult.portfolio_return * 100).toFixed(1)}%</p>
                    </div>
                    <div className="bg-[#090d16]/80 p-4 border border-[#1e293b] rounded-xl text-center">
                      <span className="text-[10px] uppercase font-bold text-[#94a3b8]">S&P 500 Return</span>
                      <p className="text-xl font-black text-[#ef4444] mt-1">{(backtestResult.spy_return * 100).toFixed(1)}%</p>
                    </div>
                    <div className="bg-[#090d16]/80 p-4 border border-[#1e293b] rounded-xl text-center">
                      <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Sharpe Ratio</span>
                      <p className="text-xl font-black text-blue-400 mt-1">{backtestResult.sharpe.toFixed(2)}</p>
                    </div>
                  </div>

                  {/* Chart rendering */}
                  <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl">
                    <h4 className="text-xs font-bold uppercase text-[#f59e0b] mb-4 tracking-wider">⏳ Cumulative Returns vs S&P 500</h4>
                    {backtestChartUrl && (
                      <img src={backtestChartUrl} alt="Backtest Results" className="rounded-lg w-full h-auto border border-[#1e293b]" />
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Individual Stock Explorer Tab */}
        {activeTab === 'explorer' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            
            {/* Search selector & actions sidebar */}
            <div className="bg-[#090d16]/60 border border-[#1e293b] p-6 rounded-xl space-y-6">
              <h3 className="text-xs font-black tracking-wider uppercase border-b border-[#1e293b] pb-2 text-[#f59e0b]">
                Search & Auditing tools
              </h3>

              {/* Add custom ticker expander */}
              <div className="border border-[#1e293b] p-4 rounded-lg bg-[#090d16]/40 space-y-3">
                <span className="text-[10px] uppercase font-bold text-[#94a3b8] block">➕ Ingest Custom Ticker / Pre-IPO</span>
                <div className="space-y-2">
                  <input
                    type="text"
                    placeholder="Ticker / Placeholder (e.g. LIME)"
                    value={customTicker}
                    onChange={(e) => setCustomTicker(e.target.value.toUpperCase())}
                    className="bg-[#090d16] border border-[#334155] rounded px-3 py-1.5 text-xs w-full uppercase focus:outline-none focus:border-[#f59e0b]"
                  />
                  <input
                    type="text"
                    placeholder="Optional SEC URL (for S-1 / unlisted)"
                    value={customSecUrl}
                    onChange={(e) => setCustomSecUrl(e.target.value)}
                    className="bg-[#090d16] border border-[#334155] rounded px-3 py-1.5 text-xs w-full focus:outline-none focus:border-[#f59e0b]"
                  />
                  <button
                    onClick={handleAddCustomTicker}
                    disabled={addingCustomTicker || !customTicker}
                    className="w-full bg-[#f59e0b] hover:bg-[#d97706] disabled:opacity-50 text-[#090d16] font-bold px-3 py-1.5 rounded text-xs uppercase transition cursor-pointer"
                  >
                    {addingCustomTicker ? 'Ingesting...' : 'Add / Ingest'}
                  </button>
                </div>
              </div>


              {/* Select stock */}
              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-2">Select Stock Ticker</label>
                <select
                  value={selectedExplorerTicker}
                  onChange={(e) => setSelectedExplorerTicker(e.target.value)}
                  className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b] font-medium"
                >
                  <option value="">-- Choose a stock --</option>
                  {allTickers.map(t => (
                    <option key={t.ticker} value={t.ticker}>{t.ticker} - {t.name}</option>
                  ))}
                </select>
              </div>

              {selectedExplorerTicker && (
                <>
                  {/* Delete button */}
                  <button
                    onClick={() => handleDeleteStock(selectedExplorerTicker)}
                    className="w-full bg-red-900/40 hover:bg-red-900/60 border border-red-800 text-red-200 font-bold py-2 px-4 rounded-lg text-xs uppercase tracking-wider transition cursor-pointer"
                  >
                    🗑️ Delete Stock from Database
                  </button>

                  <hr className="border-[#1e293b]" />

                  {/* AI audit buttons */}
                  <div className="space-y-3">
                    <span className="text-[10px] uppercase font-bold text-[#94a3b8] block">🤖 Execute AI Auditor</span>
                    
                    <button
                      onClick={() => triggerAiAudit('standard')}
                      disabled={aiAuditing}
                      className="w-full bg-[#1e293b] hover:bg-[#334155] border border-[#334155] text-left text-[#f1f5f9] px-3.5 py-2.5 rounded-lg text-xs font-semibold transition flex flex-col justify-start cursor-pointer"
                    >
                      <span>🔍 Standard AI Analysis</span>
                      <span className="text-[9px] text-[#94a3b8] mt-0.5 font-normal">Fast scan of financial ratios + business profile.</span>
                    </button>

                    <button
                      onClick={() => triggerAiAudit('source_backed')}
                      disabled={aiAuditing}
                      className="w-full bg-[#1e293b] hover:bg-[#334155] border border-[#334155] text-left text-[#f1f5f9] px-3.5 py-2.5 rounded-lg text-xs font-semibold transition flex flex-col justify-start cursor-pointer"
                    >
                      <span>🔬 Source-Backed Deep Audit</span>
                      <span className="text-[9px] text-[#94a3b8] mt-0.5 font-normal">SEC EDGAR 10-K auto-download & full RAG vector audit.</span>
                    </button>

                    <button
                      onClick={() => triggerAiAudit('multi_source')}
                      disabled={aiAuditing}
                      className="w-full bg-[#1e293b] hover:bg-[#334155] border border-[#334155] text-left text-[#f1f5f9] px-3.5 py-2.5 rounded-lg text-xs font-semibold transition flex flex-col justify-start cursor-pointer"
                    >
                      <span>🌐 Multi-Source Harvester Audit</span>
                      <span className="text-[9px] text-[#94a3b8] mt-0.5 font-normal">Cross-audits 10-Ks, call transcripts, and investor reports.</span>
                    </button>
                  </div>

                  {/* Document Uploader */}
                  <div className="border border-[#1e293b] p-4 rounded-lg bg-[#090d16]/40 space-y-3">
                    <span className="text-[10px] uppercase font-bold text-[#94a3b8] block">📤 Universal Document Uploader</span>
                    <p className="text-[9px] text-[#94a3b8]">Upload reports (PDF/TXT) to scan listings not on SEC EDGAR.</p>
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept=".pdf,.txt"
                      onChange={(e) => setUploadFile(e.target.files ? e.target.files[0] : null)}
                      className="hidden"
                    />
                    <div 
                      onClick={() => fileInputRef.current?.click()}
                      className="border border-dashed border-[#334155] rounded-lg p-4 text-center cursor-pointer hover:border-[#f59e0b] transition-colors"
                    >
                      {uploadFile ? (
                        <span className="text-xs text-[#f59e0b] font-bold block truncate">{uploadFile.name}</span>
                      ) : (
                        <span className="text-[11px] text-[#94a3b8] block">Drag & Drop or Click to Select File</span>
                      )}
                    </div>
                    <button
                      onClick={handleUploadAudit}
                      disabled={aiAuditing || !uploadFile}
                      className="w-full bg-[#10b981] hover:bg-[#059669] disabled:opacity-50 text-[#090d16] font-bold py-1.5 rounded text-xs uppercase tracking-wider transition cursor-pointer"
                    >
                      🚀 Run Audit on Document
                    </button>
                  </div>
                </>
              )}
            </div>

            {/* Main display panel */}
            <div className="lg:col-span-2 space-y-6">
              {aiAuditing && (
                <div className="bg-[#f59e0b]/10 border border-[#f59e0b]/30 p-5 rounded-xl text-center space-y-3 animate-pulse">
                  <span className="text-xl">🧠</span>
                  <p className="text-xs text-[#f59e0b] font-bold">{aiAuditStep || 'AI Model is auditing filing documents...'}</p>
                </div>
              )}

              {!selectedExplorerTicker || !explorerStockDetails ? (
                <div className="h-full border border-dashed border-[#334155] rounded-xl flex items-center justify-center text-center p-12 text-xs text-[#94a3b8]">
                  Select a ticker from the sidebar to inspect business summaries, real-time compliance drifts, progress thresholds, and AI reports.
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Ticker Name, Industry, Real-time status */}
                  <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                      <div className="flex items-center gap-3">
                        <h2 className="text-2xl font-black text-[#f1f5f9]">{explorerStockDetails.ticker}</h2>
                        <span className="text-xs text-[#94a3b8] font-bold bg-[#1e293b] px-2.5 py-1 rounded">
                          {explorerStockDetails.sector} | {explorerStockDetails.industry}
                        </span>
                      </div>
                      <p className="text-sm font-semibold text-[#94a3b8] mt-1">{explorerStockDetails.name}</p>
                      
                      {/* Real-time price compliance monitor alert display */}
                      {explorerLiveQuote && (
                        <div className="mt-3 text-xs flex flex-wrap items-center gap-2">
                          <span className="text-[#10b981] font-bold">🟢 Live price: `${explorerLiveQuote.live_price.toFixed(2)}`</span>
                          <span className="text-[#94a3b8] font-bold">| Live Cap: `${(explorerLiveQuote.live_market_cap / 1e6).toFixed(1)}M`</span>
                          
                          {/* Compliance Drift Warnings */}
                          {(() => {
                            const dbCompliant = !['F', 'Doubtful'].includes(explorerStockDetails.grade || 'F');
                            const liveCompliant = !['F', 'Doubtful'].includes(explorerLiveQuote.live_grade);
                            if (dbCompliant && !liveCompliant) {
                              return <span className="bg-[#ef4444]/20 border border-[#ef4444]/40 text-[#ef4444] px-2 py-0.5 rounded font-black animate-pulse">⚠️ CRITICAL DRIFT: Stock price drop broke compliance!</span>;
                            } else if (!dbCompliant && liveCompliant) {
                              return <span className="bg-[#10b981]/20 border border-[#10b981]/40 text-[#10b981] px-2 py-0.5 rounded font-black animate-pulse">🎉 RECOVERY: Price rise restored compliance!</span>;
                            }
                            return null;
                          })()}
                        </div>
                      )}
                    </div>

                    {/* Grade indicator */}
                    <div className="flex flex-col items-center justify-center border-2 border-[#1e293b] rounded-xl px-6 py-3 bg-[#090d16]/80 w-32">
                      <span className="text-[10px] uppercase font-black text-[#94a3b8] tracking-wider">Compliance</span>
                      <h3 className={`text-3xl font-black mt-1 ${
                        (explorerLiveQuote ? explorerLiveQuote.live_grade : explorerStockDetails.grade)?.startsWith('A') ? 'text-[#10b981]' :
                        (explorerLiveQuote ? explorerLiveQuote.live_grade : explorerStockDetails.grade)?.startsWith('B') || (explorerLiveQuote ? explorerLiveQuote.live_grade : explorerStockDetails.grade) === 'Doubtful' ? 'text-[#f59e0b]' :
                        'text-[#ef4444]'
                      }`}>
                        {explorerLiveQuote ? explorerLiveQuote.live_grade : (explorerStockDetails.grade || 'F')}
                      </h3>
                    </div>
                  </div>

                  {/* Two Column details: Business Summary vs Metrics */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    
                    {/* Summary */}
                    <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl space-y-4">
                      <h4 className="text-xs font-bold uppercase text-[#f59e0b] tracking-wider border-b border-[#1e293b] pb-2">Business Summary</h4>
                      <p className="text-xs text-[#94a3b8] leading-relaxed max-h-48 overflow-y-auto pr-2">
                        {(() => {
                          try {
                            const raw = JSON.parse(explorerStockDetails.raw_info);
                            return raw.longBusinessSummary || 'No summary description available.';
                          } catch (e) {
                            return 'No summary description available.';
                          }
                        })()}
                      </p>
                      {explorerStockDetails.sec_filing_url && (
                        <a
                          href={explorerStockDetails.sec_filing_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-block bg-[#1e293b] hover:bg-[#334155] border border-[#334155] text-[#f1f5f9] px-4 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition"
                        >
                          📄 View SEC Filings (10-K)
                        </a>
                      )}
                    </div>

                    {/* Metrics Threshold Bars */}
                    <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl space-y-4">
                      <h4 className="text-xs font-bold uppercase text-[#f59e0b] tracking-wider border-b border-[#1e293b] pb-2">Compliance Limits</h4>
                      
                      {(() => {
                        const quote = explorerLiveQuote || {
                          debt_ratio: explorerStockDetails.debt_ratio || 0,
                          cash_ratio: explorerStockDetails.cash_ratio || 0,
                          tangibility_ratio: explorerStockDetails.tangibility_ratio || 0,
                          total_haram_ratio: explorerStockDetails.total_haram_ratio || 0,
                          total_combined_ratio: (explorerStockDetails.total_haram_ratio || 0) + (explorerStockDetails.doubtful_ratio || 0),
                        };

                        const renderProgress = (val: number, limit: number, label: string, isOverridden: boolean, isCombinedCheck = false, haramVal = 0) => {
                          const pct = limit > 0 ? (val / limit) * 100 : 0;
                          let color = 'bg-[#10b981]';
                          let text = 'Passed';
                          if (val >= limit) {
                            if (isCombinedCheck && haramVal < limit) {
                              color = 'bg-[#d2691e]';
                              text = 'Doubtful';
                            } else {
                              color = 'bg-[#ef4444]';
                              text = 'Failed';
                            }
                          } else if (pct > 80) {
                            color = 'bg-[#f59e0b]';
                            text = 'Warning';
                          }

                          return (
                            <div className="space-y-1">
                              <div className="flex justify-between text-[10px] font-bold">
                                <span className="text-[#f1f5f9]">{label} {isOverridden && '✍️'}</span>
                                <span style={{ color: color.includes('10b981') ? '#10b981' : color.includes('f59e0b') ? '#f59e0b' : color.includes('d2691e') ? '#d2691e' : '#ef4444' }}>
                                  {(val * 100).toFixed(2)}% / {(limit * 100).toFixed(0)}% ({text})
                                </span>
                              </div>
                              <div className="w-full bg-[#1e293b] h-2 rounded-full overflow-hidden">
                                <div className={`${color} h-full transition-all duration-500`} style={{ width: `${Math.min(100, pct)}%` }}></div>
                              </div>
                            </div>
                          );
                        };

                        return (
                          <div className="space-y-3.5">
                            {renderProgress(
                              quote.total_haram_ratio || 0, 
                              0.05, 
                              "Haram Revenue Screen", 
                              !!(explorerStockDetails.haram_revenue_override || explorerStockDetails.interest_income_override)
                            )}
                            {renderProgress(
                              quote.total_combined_ratio || 0, 
                              0.05, 
                              "Haram + Doubtful Revenue", 
                              !!(explorerStockDetails.haram_revenue_override || explorerStockDetails.interest_income_override || explorerStockDetails.doubtful_revenue_override),
                              true,
                              quote.total_haram_ratio || 0
                            )}
                            {renderProgress(
                              quote.debt_ratio || 0, 
                              0.30, 
                              "Debt / Market Cap Screen", 
                              !isNaN(parseFloat(explorerStockDetails.debt_ratio_override))
                            )}
                            {renderProgress(
                              quote.cash_ratio || 0, 
                              0.30, 
                              "Cash / Market Cap Screen", 
                              !isNaN(parseFloat(explorerStockDetails.cash_ratio_override))
                            )}
                            {renderProgress(
                              1.0 - (quote.tangibility_ratio || 0), 
                              0.70, 
                              "Liquid Assets / Total Assets (Max 70%)", 
                              !isNaN(parseFloat(explorerStockDetails.tangibility_ratio_override))
                            )}

                            {explorerStockDetails.purification_per_share !== undefined && (
                              <div className="bg-[#10b981]/15 p-3 rounded-lg flex justify-between items-center mt-2 border border-[#10b981]/25">
                                <span className="text-[10px] uppercase font-bold text-[#10b981]">Purification oblig.</span>
                                <span className="text-xs font-extrabold text-[#10b981]">${(explorerStockDetails.purification_per_share || 0).toFixed(4)} / share</span>
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  </div>

                  {/* AI Compliance report & visual charts breakdown */}
                  {explorerStockDetails.override_reason && (
                    <div className="bg-[#090d16]/40 p-6 border border-[#1e293b] rounded-xl space-y-6">
                      <div className="bg-blue-950/20 border border-blue-900/40 p-5 rounded-xl">
                        <h4 className="text-xs font-bold uppercase text-blue-400 mb-2 flex items-center gap-2">
                          <span>🤖</span> AI Auditor Verdict Summary
                          {aiVerdict?.audit_source && (
                            <span className="text-[9px] bg-blue-900 text-blue-200 px-2 py-0.5 rounded uppercase font-black tracking-wider">
                              {aiVerdict.audit_source}
                            </span>
                          )}
                        </h4>
                        <p className="text-xs text-[#94a3b8] leading-relaxed font-medium">
                          {aiVerdict?.reasoning || explorerStockDetails.override_reason}
                        </p>
                      </div>

                      {/* Financial balance breakdown & Donut chart */}
                      {aiVerdict && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          
                          {/* Financial numbers */}
                          <div className="text-xs space-y-3 font-medium text-[#94a3b8]">
                            <span className="text-[10px] uppercase font-bold text-[#f1f5f9] block border-b border-[#1e293b] pb-1">Balance Sheet Audit Details</span>
                            <div className="flex justify-between">
                              <span>36-Mo Avg Market Cap:</span>
                              <span className="text-[#f1f5f9] font-black">${((explorerStockDetails.avg_market_cap_36mo || 0) / 1e6).toFixed(1)}M</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Total assets in filing:</span>
                              <span className="text-[#f1f5f9] font-black">${((explorerStockDetails.total_assets || 0) / 1e6).toFixed(1)}M</span>
                            </div>
                            <hr className="border-[#1e293b]" />
                            <div className="flex justify-between">
                              <span>Total Reported Revenue:</span>
                              <span className="text-[#f1f5f9] font-black">${(aiVerdict.total_revenue_millions || 0).toFixed(1)}M</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Haram Revenue Segment:</span>
                              <span className="text-[#ef4444] font-black">${(aiVerdict.haram_revenue_millions || 0).toFixed(1)}M</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Interest Income Component:</span>
                              <span className="text-[#f59e0b] font-black">${(aiVerdict.interest_income_millions || 0).toFixed(1)}M</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Doubtful Revenue Segment:</span>
                              <span className="text-[#d2691e] font-black">${(aiVerdict.doubtful_revenue_millions || 0).toFixed(1)}M</span>
                            </div>
                            <hr className="border-[#1e293b]" />
                            <div className="flex justify-between">
                              <span>Interest-bearing Debt:</span>
                              <span className="text-[#f1f5f9] font-black">${(aiVerdict.interest_bearing_debt_millions || 0).toFixed(1)}M</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Total Cash & Marketable Securities:</span>
                              <span className="text-[#f1f5f9] font-black">${(aiVerdict.total_cash_and_securities_millions || 0).toFixed(1)}M</span>
                            </div>
                          </div>

                          {/* Dynamic SVG donut revenue chart */}
                          <div className="flex flex-col items-center justify-center bg-[#090d16]/30 p-4 border border-[#1e293b]/50 rounded-xl">
                            <span className="text-[10px] uppercase font-bold text-[#f1f5f9] mb-4 tracking-wider">Revenue Breakdown Shares</span>
                            
                            {(() => {
                              const tot = aiVerdict.total_revenue_millions || 1.0;
                              const haram = aiVerdict.haram_revenue_millions || 0.0;
                              const interest = aiVerdict.interest_income_millions || 0.0;
                              const doubtful = aiVerdict.doubtful_revenue_millions || 0.0;
                              const halal = Math.max(0, tot - (haram + interest + doubtful));

                              const haramPct = haram / tot;
                              const intPct = interest / tot;
                              const doubtPct = doubtful / tot;
                              const halalPct = halal / tot;

                              return (
                                <div className="space-y-4 w-full">
                                  {/* Segmented bar */}
                                  <div className="w-full h-4 rounded-full overflow-hidden flex bg-[#1e293b]">
                                    {halalPct > 0 && <div className="bg-[#10b981] h-full" style={{ width: `${halalPct * 100}%` }} title={`Halal: ${(halalPct*100).toFixed(1)}%`}></div>}
                                    {haramPct > 0 && <div className="bg-[#ef4444] h-full" style={{ width: `${haramPct * 100}%` }} title={`Haram: ${(haramPct*100).toFixed(1)}%`}></div>}
                                    {intPct > 0 && <div className="bg-[#f59e0b] h-full" style={{ width: `${intPct * 100}%` }} title={`Interest: ${(intPct*100).toFixed(1)}%`}></div>}
                                    {doubtPct > 0 && <div className="bg-[#d2691e] h-full" style={{ width: `${doubtPct * 100}%` }} title={`Doubtful: ${(doubtPct*100).toFixed(1)}%`}></div>}
                                  </div>

                                  {/* Legend list */}
                                  <div className="grid grid-cols-2 gap-2 text-[10px] font-bold text-[#94a3b8]">
                                    <div className="flex items-center gap-1.5">
                                      <span className="w-2.5 h-2.5 rounded-full bg-[#10b981] inline-block"></span>
                                      <span>Halal: {(halalPct*100).toFixed(1)}%</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                      <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444] inline-block"></span>
                                      <span>Haram: {(haramPct*100).toFixed(1)}%</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                      <span className="w-2.5 h-2.5 rounded-full bg-[#f59e0b] inline-block"></span>
                                      <span>Interest: {(intPct*100).toFixed(1)}%</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                      <span className="w-2.5 h-2.5 rounded-full bg-[#d2691e] inline-block"></span>
                                      <span>Doubtful: {(doubtPct*100).toFixed(1)}%</span>
                                    </div>
                                  </div>
                                </div>
                              );
                            })()}
                          </div>

                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Shariah Segment Map Rules Tab */}
        {activeTab === 'rules' && (
          <div className="bg-[#090d16]/40 border border-[#1e293b] rounded-xl p-6 space-y-8">
            <div>
              <h2 className="text-base font-bold uppercase tracking-wider text-[#f59e0b] mb-1">
                ⚙️ Active Shariah Segment Rules (AI-Generated)
              </h2>
              <p className="text-xs text-[#94a3b8]">
                Displaying segment patterns and overrides mapping conglomerate services committed dynamically during deep vector searches.
              </p>
            </div>

            {rulesLoading ? (
              <div className="text-center py-8 text-xs text-[#94a3b8] animate-pulse">Loading compliance mapping patterns...</div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Ticker specific rules */}
                <div className="space-y-4">
                  <h3 className="text-xs font-black uppercase text-[#f59e0b] tracking-wider border-b border-[#1e293b] pb-2 flex justify-between items-center">
                    <span>🎯 Ticker-Specific Rules</span>
                    <span className="bg-[#1e293b] px-2 py-0.5 rounded text-[10px] text-[#94a3b8]">{tickerRules.length} Rules</span>
                  </h3>

                  <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
                    {tickerRules.length === 0 ? (
                      <div className="text-xs text-[#94a3b8] italic">No active ticker segment overrides.</div>
                    ) : (
                      tickerRules.map((rule, idx) => (
                        <div key={idx} className="p-3 border border-[#1e293b] rounded bg-[#090d16]/30 flex justify-between items-start gap-4">
                          <div>
                            <span className="text-[10px] font-black uppercase text-[#f59e0b] block">{rule.ticker}</span>
                            <span className="text-[11px] font-semibold text-[#f1f5f9] block mt-0.5">`{rule.segment_name}`</span>
                            <p className="text-[10px] text-[#94a3b8] mt-1 italic">{rule.notes}</p>
                          </div>
                          <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase ${
                            rule.compliance_status === 'halal' ? 'bg-[#10b981]/25 text-[#10b981]' :
                            rule.compliance_status === 'doubtful' ? 'bg-[#f59e0b]/25 text-[#f59e0b]' :
                            'bg-[#ef4444]/25 text-[#ef4444]'
                          }`}>
                            {rule.compliance_status}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Global segment rules */}
                <div className="space-y-4">
                  <h3 className="text-xs font-black uppercase text-[#f59e0b] tracking-wider border-b border-[#1e293b] pb-2 flex justify-between items-center">
                    <span>🌐 Global Keyword Patterns</span>
                    <span className="bg-[#1e293b] px-2 py-0.5 rounded text-[10px] text-[#94a3b8]">{globalRules.length} Patterns</span>
                  </h3>

                  <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
                    {globalRules.length === 0 ? (
                      <div className="text-xs text-[#94a3b8] italic">No active global pattern mappings.</div>
                    ) : (
                      globalRules.map((rule, idx) => (
                        <div key={idx} className="p-3 border border-[#1e293b] rounded bg-[#090d16]/30 flex justify-between items-start gap-4">
                          <div>
                            <code className="text-xs font-bold text-[#f59e0b] block">`{rule.pattern}`</code>
                            <p className="text-[10px] text-[#94a3b8] mt-1.5 italic">{rule.notes}</p>
                          </div>
                          <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase ${
                            rule.compliance_status === 'halal' ? 'bg-[#10b981]/25 text-[#10b981]' :
                            rule.compliance_status === 'doubtful' ? 'bg-[#f59e0b]/25 text-[#f59e0b]' :
                            'bg-[#ef4444]/25 text-[#ef4444]'
                          }`}>
                            {rule.compliance_status}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>
            )}
          </div>
        )}

        {/* SRE Heath Telemetry Tab */}
        {activeTab === 'mcp' && (
          <div className="bg-[#090d16]/40 border border-[#1e293b] rounded-xl p-6 space-y-6">
            <div>
              <h2 className="text-base font-bold uppercase tracking-wider text-[#f59e0b] mb-1">
                🤖 SRE Agent Health Telemetry
              </h2>
              <p className="text-xs text-[#94a3b8]">
                Real-time diagnostic checks, maintenance actions, and connection status for the local autonomous agent.
              </p>
            </div>

            {mcpLoading ? (
              <div className="text-center py-8 text-xs text-[#94a3b8] animate-pulse">Reading system status.json...</div>
            ) : !mcpStatus ? (
              <div className="text-center py-8 text-xs text-[#94a3b8]">No connection status metrics. Is the SRE Agent running?</div>
            ) : (
              <div className="space-y-6">
                {/* Metric metrics */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  
                  <div className="bg-[#090d16]/80 p-5 border border-[#1e293b] rounded-xl text-center space-y-1">
                    <span className="text-[10px] uppercase font-bold text-[#94a3b8]">System health status</span>
                    <div className="text-lg font-black text-[#10b981] flex items-center justify-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#10b981] inline-block animate-ping"></span>
                      {mcpStatus.system?.status || 'Active'}
                    </div>
                  </div>

                  <div className="bg-[#090d16]/80 p-5 border border-[#1e293b] rounded-xl text-center space-y-1">
                    <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Last action outcome</span>
                    <p className={`text-lg font-black uppercase ${mcpStatus.last_action?.result === 'success' ? 'text-[#10b981]' : 'text-[#f59e0b]'}`}>
                      {mcpStatus.last_action?.result || 'success'}
                    </p>
                  </div>

                  <div className="bg-[#090d16]/80 p-5 border border-[#1e293b] rounded-xl text-center space-y-1">
                    <span className="text-[10px] uppercase font-bold text-[#94a3b8]">Last Updated at</span>
                    <p className="text-sm font-semibold text-[#f1f5f9] mt-1">{mcpStatus.timestamp || 'N/A'}</p>
                  </div>

                </div>

                {/* Details layout */}
                <div className="bg-[#090d16]/60 border border-[#1e293b]/70 p-5 rounded-xl space-y-3 text-xs">
                  <div className="flex justify-between">
                    <span className="font-bold text-[#94a3b8]">Last Trigger Action Type:</span>
                    <span className="text-[#f1f5f9] font-black uppercase bg-[#1e293b] px-2 py-0.5 rounded">{mcpStatus.last_action?.type || 'Diagnostic check'}</span>
                  </div>
                  <hr className="border-[#1e293b]" />
                  <div className="space-y-1">
                    <span className="font-bold text-[#94a3b8] block">Agent Operations Notes:</span>
                    <p className="text-[#f1f5f9] leading-relaxed font-semibold italic bg-[#090d16] p-3 border border-[#1e293b] rounded">
                      {mcpStatus.last_action?.notes || 'System performing regular automated sweeps. Container services executing correctly.'}
                    </p>
                  </div>
                </div>

                {/* Raw View JSON */}
                <details className="group border border-[#1e293b] rounded-lg overflow-hidden bg-[#090d16]/20">
                  <summary className="cursor-pointer bg-[#090d16]/60 p-4 text-xs font-bold text-[#94a3b8] select-none hover:text-[#f1f5f9] flex justify-between items-center">
                    <span>🐞 View Raw Telemetry Logs</span>
                    <span className="transition-transform group-open:rotate-180">▼</span>
                  </summary>
                  <div className="p-4 bg-[#05080f] font-mono text-[10px] overflow-x-auto text-[#10b981]">
                    <pre>{JSON.stringify(mcpStatus, null, 2)}</pre>
                  </div>
                </details>
              </div>
            )}
          </div>
        )}

        {/* Manual Overrides Propose Form Tab */}
        {activeTab === 'overrides' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <form onSubmit={submitOverride} className="bg-[#090d16]/60 border border-[#1e293b] p-6 rounded-xl space-y-4">
              <h3 className="text-xs font-black tracking-wider uppercase border-b border-[#1e293b] pb-2 text-[#f59e0b]">
                Propose Manual Compliance Override
              </h3>

              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Stock Ticker *</label>
                <input
                  type="text" required placeholder="e.g. AAPL"
                  value={manualTicker} onChange={(e) => setManualTicker(e.target.value.toUpperCase())}
                  className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b] uppercase font-medium"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Non-compliant Revenue (%)</label>
                  <input
                    type="number" step="0.001" placeholder="e.g. 0.025"
                    value={manualHaramRevenue} onChange={(e) => setManualHaramRevenue(e.target.value)}
                    className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b]"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Debt-to-Asset Ratio (%)</label>
                  <input
                    type="number" step="0.001" placeholder="e.g. 0.28"
                    value={manualDebtRatio} onChange={(e) => setManualDebtRatio(e.target.value)}
                    className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase font-bold text-[#94a3b8] mb-1">Override Justification *</label>
                <textarea
                  required placeholder="Describe segment checks, revenue breakdown, or source files..."
                  value={manualReason} onChange={(e) => setManualReason(e.target.value)}
                  className="w-full bg-[#090d16] border border-[#334155] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#f59e0b] h-24 font-medium"
                />
              </div>

              <button
                type="submit"
                className="w-full bg-[#10b981] hover:bg-[#059669] text-[#090d16] font-black py-2.5 px-4 rounded-lg text-xs tracking-wider uppercase transition cursor-pointer"
              >
                💾 Save Override & Re-scan
              </button>
            </form>

            <div className="bg-[#090d16]/30 border border-[#1e293b] p-6 rounded-xl">
              <h3 className="text-xs font-black tracking-wider uppercase border-b border-[#1e293b] pb-2 text-[#94a3b8]">
                Qualitative Review Policy (AAOIFI Standard)
              </h3>
              <ul className="text-xs text-[#94a3b8] space-y-3.5 mt-4 list-disc pl-4 leading-relaxed font-semibold">
                <li><strong>Primary Activity</strong>: Must be fundamentally halal. Prohibited activities must represent less than <strong>5%</strong> of gross revenues.</li>
                <li><strong>Interest-Bearing Debt</strong>: Total debt divided by 36-month average market capitalization must be less than <strong>30%</strong>.</li>
                <li><strong>Interest-Bearing Cash</strong>: Cash plus interest-yielding securities divided by market capitalization must be less than <strong>30%</strong>.</li>
                <li><strong>Receivables</strong>: Accounts receivable divided by market capitalization must be less than <strong>30%</strong>.</li>
                <li><strong>Purification</strong>: Investment portfolios must deduct and purify non-compliant interest or prohibited segment dividends.</li>
              </ul>
            </div>
          </div>
        )}

      </section>
    </main>
  );
}