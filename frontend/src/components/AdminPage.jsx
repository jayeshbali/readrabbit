import React, { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

const emptyArticle = {
  title: '',
  url: '',
  source: '',
  author: '',
  summary: '',
  topics: [],
  read_time: null
}

function AdminPage({ onBack }) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [articles, setArticles] = useState([])
  const [stats, setStats] = useState(null)
  
  // Toggle between AI, Manual, and Discover mode
  const [addMode, setAddMode] = useState('discover') // 'ai' | 'manual' | 'discover'
  const [manualForm, setManualForm] = useState(emptyArticle)

  // Discovery state
  const [discoverMode, setDiscoverMode] = useState('auto') // 'auto' | 'topic' | 'source' | 'similar'
  const [discoverInput, setDiscoverInput] = useState('')
  const [selectedArticleId, setSelectedArticleId] = useState('')
  const [candidates, setCandidates] = useState([])
  const [discoverContext, setDiscoverContext] = useState('')
  const [libraryClusters, setLibraryClusters] = useState([])
  const [approving, setApproving] = useState({}) // Track which URLs are being approved

  // Fetch stats and articles on mount
  useEffect(() => {
    fetchStats()
    fetchArticles()
  }, [])

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/stats`)
      const data = await res.json()
      setStats(data)
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    }
  }

  const fetchArticles = async () => {
    try {
      const res = await fetch(`${API_BASE}/articles?limit=100`)
      const data = await res.json()
      setArticles(data.articles || [])
    } catch (err) {
      console.error('Failed to fetch articles:', err)
    }
  }

  const handleExtract = async () => {
    if (!url.trim()) return
    
    setLoading(true)
    setError(null)
    setPreview(null)
    
    try {
      const res = await fetch(`${API_BASE}/admin/extract-metadata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to extract metadata')
      }
      
      setPreview({ url: url.trim(), ...data.metadata })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!preview) return
    
    setLoading(true)
    setError(null)
    
    try {
      const res = await fetch(`${API_BASE}/articles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(preview)
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save article')
      }
      
      setSuccess(`Added: ${preview.title}`)
      setPreview(null)
      setUrl('')
      fetchStats()
      fetchArticles()
      
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleQuickAdd = async () => {
    if (!url.trim()) return
    
    setLoading(true)
    setError(null)
    
    try {
      const res = await fetch(`${API_BASE}/admin/add-article-smart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to add article')
      }
      
      setSuccess(`Added: ${data.article.title}`)
      setUrl('')
      fetchStats()
      fetchArticles()
      
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleManualSave = async () => {
    if (!manualForm.title.trim() || !manualForm.url.trim()) {
      setError('Title and URL are required')
      return
    }
    
    setLoading(true)
    setError(null)
    
    try {
      const res = await fetch(`${API_BASE}/articles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...manualForm,
          topics: manualForm.topics,
          read_time: manualForm.read_time || null
        })
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save article')
      }
      
      setSuccess(`Added: ${manualForm.title}`)
      setManualForm(emptyArticle)
      fetchStats()
      fetchArticles()
      
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (articleId, articleTitle) => {
    if (!confirm(`Delete "${articleTitle}"?`)) return
    
    try {
      const res = await fetch(`${API_BASE}/articles/${articleId}`, {
        method: 'DELETE'
      })
      
      if (!res.ok) {
        throw new Error('Failed to delete article')
      }
      
      fetchStats()
      fetchArticles()
    } catch (err) {
      setError(err.message)
    }
  }

  // Discovery functions
  const handleDiscover = async () => {
    setLoading(true)
    setError(null)
    setCandidates([])
    setDiscoverContext('')
    
    try {
      const body = {
        mode: discoverMode,
        count: 5,
        match_library_style: true
      }
      
      if (discoverMode === 'topic') {
        if (!discoverInput.trim()) {
          setError('Please enter a topic')
          setLoading(false)
          return
        }
        body.topic = discoverInput.trim()
      } else if (discoverMode === 'source') {
        if (!discoverInput.trim()) {
          setError('Please enter an author or source name')
          setLoading(false)
          return
        }
        body.source = discoverInput.trim()
      } else if (discoverMode === 'similar') {
        if (!selectedArticleId) {
          setError('Please select an article')
          setLoading(false)
          return
        }
        body.similar_to = selectedArticleId
      }
      
      const res = await fetch(`${API_BASE}/admin/candidates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to discover articles')
      }
      
      setCandidates(data.candidates || [])
      setDiscoverContext(data.context || '')
      setLibraryClusters(data.library_stats?.clusters || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleApproveCandidate = async (candidateUrl, candidateTitle) => {
    setApproving(prev => ({ ...prev, [candidateUrl]: true }))
    setError(null)
    
    try {
      const res = await fetch(`${API_BASE}/admin/candidates/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: candidateUrl })
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to approve article')
      }
      
      // Remove from candidates list
      setCandidates(prev => prev.filter(c => c.url !== candidateUrl))
      
      setSuccess(`Added: ${candidateTitle}`)
      fetchStats()
      fetchArticles()
      
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setApproving(prev => ({ ...prev, [candidateUrl]: false }))
    }
  }

  const handleSkipCandidate = (candidateUrl) => {
    setCandidates(prev => prev.filter(c => c.url !== candidateUrl))
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-3 sm:px-4 py-3 sm:py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 sm:gap-3">
              <button
                onClick={onBack}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <h1 className="text-lg sm:text-xl font-bold text-gray-900">Admin</h1>
            </div>
            
            {stats && (
              <div className="flex items-center gap-2 sm:gap-4 text-xs sm:text-sm text-gray-600">
                <span><strong>{stats.total}</strong> articles</span>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-3 sm:px-4 py-4 sm:py-6 space-y-4 sm:space-y-6">
        {/* Success/Error Messages */}
        {success && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
            {success}
          </div>
        )}
        
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Add Article Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-6">
          {/* Mode Toggle */}
          <div className="flex gap-1 mb-4 sm:mb-6 bg-gray-100 p-1 rounded-lg">
            <button
              onClick={() => setAddMode('discover')}
              className={`flex-1 py-2 px-2 sm:px-4 rounded-md text-xs sm:text-sm font-medium transition-colors ${
                addMode === 'discover' 
                  ? 'bg-white text-orange-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              🔍 AI Discovery
            </button>
            <button
              onClick={() => setAddMode('ai')}
              className={`flex-1 py-2 px-2 sm:px-4 rounded-md text-xs sm:text-sm font-medium transition-colors ${
                addMode === 'ai' 
                  ? 'bg-white text-orange-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              🤖 Add by URL
            </button>
            <button
              onClick={() => setAddMode('manual')}
              className={`flex-1 py-2 px-2 sm:px-4 rounded-md text-xs sm:text-sm font-medium transition-colors ${
                addMode === 'manual' 
                  ? 'bg-white text-orange-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              ✏️ Manual
            </button>
          </div>

          {/* AI Discovery Mode */}
          {addMode === 'discover' && (
            <div className="space-y-4">
              {/* Discovery Mode Selector */}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => { setDiscoverMode('auto'); setDiscoverInput(''); }}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    discoverMode === 'auto'
                      ? 'bg-orange-100 text-orange-700 border border-orange-200'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  ✨ Auto
                </button>
                <button
                  onClick={() => { setDiscoverMode('topic'); setDiscoverInput(''); }}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    discoverMode === 'topic'
                      ? 'bg-orange-100 text-orange-700 border border-orange-200'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  📝 Topic
                </button>
                <button
                  onClick={() => { setDiscoverMode('source'); setDiscoverInput(''); }}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    discoverMode === 'source'
                      ? 'bg-orange-100 text-orange-700 border border-orange-200'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  👤 Author
                </button>
                <button
                  onClick={() => { setDiscoverMode('similar'); setDiscoverInput(''); setSelectedArticleId(''); }}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    discoverMode === 'similar'
                      ? 'bg-orange-100 text-orange-700 border border-orange-200'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  🔗 Similar
                </button>
              </div>

              {/* Input based on mode */}
              {discoverMode === 'auto' && (
                <div className="text-sm text-gray-500 bg-gray-50 p-3 rounded-lg">
                  AI will discover articles based on your library clusters: 
                  {libraryClusters.length > 0 
                    ? ' ' + libraryClusters.map(c => c.name).join(', ')
                    : ' Startups, Philosophy, Psychology...'}
                </div>
              )}

              {discoverMode === 'topic' && (
                <input
                  type="text"
                  value={discoverInput}
                  onChange={(e) => setDiscoverInput(e.target.value)}
                  placeholder="e.g., decision making, stoicism, mental models"
                  className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  onKeyDown={(e) => e.key === 'Enter' && handleDiscover()}
                />
              )}

              {discoverMode === 'source' && (
                <input
                  type="text"
                  value={discoverInput}
                  onChange={(e) => setDiscoverInput(e.target.value)}
                  placeholder="e.g., Paul Graham, Morgan Housel, Farnam Street"
                  className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  onKeyDown={(e) => e.key === 'Enter' && handleDiscover()}
                />
              )}

              {discoverMode === 'similar' && (
                <select
                  value={selectedArticleId}
                  onChange={(e) => setSelectedArticleId(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm bg-white"
                >
                  <option value="">Select an article to find similar...</option>
                  {articles.map(article => (
                    <option key={article.id} value={article.id}>
                      {article.title}
                    </option>
                  ))}
                </select>
              )}

              {/* Discover Button */}
              <button
                onClick={handleDiscover}
                disabled={loading}
                className="w-full py-3 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Discovering...
                  </span>
                ) : (
                  'Find Articles'
                )}
              </button>

              {/* Context Message */}
              {discoverContext && (
                <div className="text-xs text-gray-500 text-center">
                  {discoverContext}
                </div>
              )}

              {/* Candidates List */}
              {candidates.length > 0 && (
                <div className="space-y-3 pt-2">
                  <h3 className="text-sm font-medium text-gray-700">
                    Found {candidates.length} candidates
                  </h3>
                  
                  {candidates.map((candidate, idx) => (
                    <div 
                      key={idx}
                      className="border border-gray-200 rounded-lg p-4 space-y-2 hover:border-gray-300 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <a 
                            href={candidate.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-gray-900 hover:text-orange-600 text-sm line-clamp-2"
                          >
                            {candidate.title}
                          </a>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <span className="text-xs text-gray-500">{candidate.source}</span>
                            {candidate.match_score && (
                              <span className={`text-xs px-2 py-0.5 rounded-full ${
                                candidate.match_score >= 85 
                                  ? 'bg-green-100 text-green-700'
                                  : candidate.match_score >= 70
                                  ? 'bg-yellow-100 text-yellow-700'
                                  : 'bg-gray-100 text-gray-600'
                              }`}>
                                {candidate.match_score}% match
                              </span>
                            )}
                            {candidate.matched_cluster && (
                              <span className="text-xs text-gray-400">
                                → {candidate.matched_cluster}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      
                      {candidate.snippet && (
                        <p className="text-xs text-gray-500 line-clamp-2">
                          {candidate.snippet}
                        </p>
                      )}
                      
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          onClick={() => handleApproveCandidate(candidate.url, candidate.title)}
                          disabled={approving[candidate.url]}
                          className="flex-1 py-2 bg-green-500 text-white text-sm font-medium rounded-lg hover:bg-green-600 disabled:opacity-50 transition-colors"
                        >
                          {approving[candidate.url] ? 'Adding...' : '✓ Add to Library'}
                        </button>
                        <button
                          onClick={() => handleSkipCandidate(candidate.url)}
                          className="px-4 py-2 text-gray-500 text-sm font-medium rounded-lg hover:bg-gray-100 transition-colors"
                        >
                          Skip
                        </button>
                        <a
                          href={candidate.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-2 text-gray-400 hover:text-gray-600 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Empty State */}
              {!loading && candidates.length === 0 && discoverContext && (
                <div className="text-center py-6 text-gray-500 text-sm">
                  No candidates found. Try a different search.
                </div>
              )}
            </div>
          )}

          {/* AI Mode - Add by URL */}
          {addMode === 'ai' && (
            <>
              <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste article URL..."
                  className="flex-1 px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  onKeyDown={(e) => e.key === 'Enter' && handleQuickAdd()}
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleQuickAdd}
                    disabled={loading || !url.trim()}
                    className="flex-1 sm:flex-none px-4 sm:px-5 py-3 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm whitespace-nowrap"
                  >
                    {loading ? 'Adding...' : 'Quick Add'}
                  </button>
                  <button
                    onClick={handleExtract}
                    disabled={loading || !url.trim()}
                    className="flex-1 sm:flex-none px-4 sm:px-5 py-3 border border-gray-200 text-gray-700 font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm whitespace-nowrap"
                  >
                    Preview
                  </button>
                </div>
              </div>

              {/* Preview Card */}
              {preview && (
                <div className="mt-4 sm:mt-6 border border-gray-200 rounded-lg p-3 sm:p-4 space-y-3">
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-gray-500 uppercase tracking-wide">Title</label>
                      <input
                        type="text"
                        value={preview.title || ''}
                        onChange={(e) => setPreview({...preview, title: e.target.value})}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 text-sm"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Source</label>
                        <input
                          type="text"
                          value={preview.source || ''}
                          onChange={(e) => setPreview({...preview, source: e.target.value})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Author</label>
                        <input
                          type="text"
                          value={preview.author || ''}
                          onChange={(e) => setPreview({...preview, author: e.target.value})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 text-sm"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="text-xs text-gray-500 uppercase tracking-wide">Summary</label>
                      <textarea
                        value={preview.summary || ''}
                        onChange={(e) => setPreview({...preview, summary: e.target.value})}
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 text-sm"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Topics (comma-separated)</label>
                        <input
                          type="text"
                          value={(preview.topics || []).join(', ')}
                          onChange={(e) => setPreview({...preview, topics: e.target.value.split(',').map(t => t.trim()).filter(Boolean)})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Read Time (min)</label>
                        <input
                          type="number"
                          value={preview.read_time || ''}
                          onChange={(e) => setPreview({...preview, read_time: parseInt(e.target.value) || null})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 text-sm"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => setPreview(null)}
                      className="px-4 py-2 text-gray-600 hover:text-gray-800 text-sm"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={loading}
                      className="px-4 sm:px-5 py-2 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 text-sm"
                    >
                      Save Article
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Manual Mode */}
          {addMode === 'manual' && (
            <div className="space-y-3 sm:space-y-4">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">URL *</label>
                <input
                  type="url"
                  value={manualForm.url}
                  onChange={(e) => setManualForm({...manualForm, url: e.target.value})}
                  placeholder="https://example.com/article"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Title *</label>
                <input
                  type="text"
                  value={manualForm.title}
                  onChange={(e) => setManualForm({...manualForm, title: e.target.value})}
                  placeholder="Article title"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                />
              </div>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Source</label>
                  <input
                    type="text"
                    value={manualForm.source}
                    onChange={(e) => setManualForm({...manualForm, source: e.target.value})}
                    placeholder="e.g., Paul Graham"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Author</label>
                  <input
                    type="text"
                    value={manualForm.author}
                    onChange={(e) => setManualForm({...manualForm, author: e.target.value})}
                    placeholder="Author name"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Summary</label>
                <textarea
                  value={manualForm.summary}
                  onChange={(e) => setManualForm({...manualForm, summary: e.target.value})}
                  rows={2}
                  placeholder="Brief description"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Topics (comma-separated)</label>
                  <input
                    type="text"
                    value={manualForm.topics.join(', ')}
                    onChange={(e) => setManualForm({...manualForm, topics: e.target.value.split(',').map(t => t.trim()).filter(Boolean)})}
                    placeholder="AI, Productivity"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Read Time (min)</label>
                  <input
                    type="number"
                    value={manualForm.read_time || ''}
                    onChange={(e) => setManualForm({...manualForm, read_time: parseInt(e.target.value) || null})}
                    placeholder="10"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={handleManualSave}
                  disabled={loading || !manualForm.title.trim() || !manualForm.url.trim()}
                  className="w-full sm:w-auto px-6 py-2.5 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
                >
                  {loading ? 'Saving...' : 'Save Article'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Articles List */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-6">
          <h2 className="text-base sm:text-lg font-semibold text-gray-900 mb-4">All Articles ({articles.length})</h2>
          
          <div className="space-y-2 sm:space-y-3">
            {articles.map((article) => (
              <div 
                key={article.id}
                className="flex items-start sm:items-center justify-between p-2 sm:p-3 bg-gray-50 rounded-lg gap-2"
              >
                <div className="flex-1 min-w-0">
                  <a 
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-gray-900 hover:text-orange-600 text-sm sm:text-base line-clamp-1"
                  >
                    {article.title}
                  </a>
                  <div className="text-xs sm:text-sm text-gray-500 flex flex-wrap items-center gap-1 sm:gap-2 mt-1">
                    <span className="truncate max-w-[100px] sm:max-w-none">{article.source}</span>
                    {article.read_time && (
                      <>
                        <span>·</span>
                        <span>{article.read_time}m</span>
                      </>
                    )}
                    <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${
                      article.source_type === 'AI Suggested' 
                        ? 'bg-purple-100 text-purple-700' 
                        : 'bg-gray-200 text-gray-600'
                    }`}>
                      {article.source_type === 'AI Suggested' ? 'AI' : 'Manual'}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(article.id, article.title)}
                  className="p-1.5 sm:p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg flex-shrink-0"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
            
            {articles.length === 0 && (
              <p className="text-gray-500 text-center py-8 text-sm">No articles yet. Add your first one above!</p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

export default AdminPage
