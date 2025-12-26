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
  
  // New: Toggle between AI and Manual mode
  const [addMode, setAddMode] = useState('ai') // 'ai' | 'manual'
  const [manualForm, setManualForm] = useState(emptyArticle)

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
      
      // Clear success message after 3 seconds
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

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={onBack}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <h1 className="text-xl font-bold text-gray-900">Admin</h1>
            </div>
            
            {stats && (
              <div className="text-sm text-gray-500">
                {stats.total_articles} articles
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Add Article Section */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Add Article</h2>
            
            {/* Mode Toggle */}
            <div className="flex items-center bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setAddMode('ai')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  addMode === 'ai' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                🤖 AI Auto-fill
              </button>
              <button
                onClick={() => setAddMode('manual')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  addMode === 'manual' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                ✏️ Manual
              </button>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 bg-red-50 text-red-700 rounded-lg mb-4">
              {error}
            </div>
          )}

          {/* Success */}
          {success && (
            <div className="p-3 bg-green-50 text-green-700 rounded-lg mb-4">
              ✓ {success}
            </div>
          )}

          {/* AI Mode */}
          {addMode === 'ai' && (
            <>
              {/* URL Input */}
              <div className="flex gap-3 mb-4">
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste article URL..."
                  className="flex-1 px-4 py-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  onKeyDown={(e) => e.key === 'Enter' && handleExtract()}
                />
                <button
                  onClick={handleExtract}
                  disabled={loading || !url.trim()}
                  className="px-5 py-2.5 bg-gray-100 text-gray-700 font-medium rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Preview
                </button>
                <button
                  onClick={handleQuickAdd}
                  disabled={loading || !url.trim()}
                  className="px-5 py-2.5 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Adding...' : 'Quick Add'}
                </button>
              </div>

              {/* Preview */}
              {preview && (
                <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                  <h3 className="font-semibold text-gray-900 mb-2">Preview</h3>
                  
                  <div className="space-y-3 mb-4">
                    <div>
                      <label className="text-xs text-gray-500 uppercase tracking-wide">Title</label>
                      <input
                        type="text"
                        value={preview.title || ''}
                        onChange={(e) => setPreview({...preview, title: e.target.value})}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1"
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Source</label>
                        <input
                          type="text"
                          value={preview.source || ''}
                          onChange={(e) => setPreview({...preview, source: e.target.value})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Author</label>
                        <input
                          type="text"
                          value={preview.author || ''}
                          onChange={(e) => setPreview({...preview, author: e.target.value})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="text-xs text-gray-500 uppercase tracking-wide">Summary</label>
                      <textarea
                        value={preview.summary || ''}
                        onChange={(e) => setPreview({...preview, summary: e.target.value})}
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Topics (comma-separated)</label>
                        <input
                          type="text"
                          value={(preview.topics || []).join(', ')}
                          onChange={(e) => setPreview({...preview, topics: e.target.value.split(',').map(t => t.trim()).filter(Boolean)})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase tracking-wide">Read Time (min)</label>
                        <input
                          type="number"
                          value={preview.read_time || ''}
                          onChange={(e) => setPreview({...preview, read_time: parseInt(e.target.value) || null})}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => setPreview(null)}
                      className="px-4 py-2 text-gray-600 hover:text-gray-800"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={loading}
                      className="px-5 py-2 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50"
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
            <div className="space-y-4">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">URL *</label>
                <input
                  type="url"
                  value={manualForm.url}
                  onChange={(e) => setManualForm({...manualForm, url: e.target.value})}
                  placeholder="https://example.com/article"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Title *</label>
                <input
                  type="text"
                  value={manualForm.title}
                  onChange={(e) => setManualForm({...manualForm, title: e.target.value})}
                  placeholder="Article title"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                />
              </div>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Source</label>
                  <input
                    type="text"
                    value={manualForm.source}
                    onChange={(e) => setManualForm({...manualForm, source: e.target.value})}
                    placeholder="e.g., Paul Graham, The New Yorker"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Author</label>
                  <input
                    type="text"
                    value={manualForm.author}
                    onChange={(e) => setManualForm({...manualForm, author: e.target.value})}
                    placeholder="Author name"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Summary</label>
                <textarea
                  value={manualForm.summary}
                  onChange={(e) => setManualForm({...manualForm, summary: e.target.value})}
                  rows={2}
                  placeholder="Brief description that makes someone want to read it"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Topics (comma-separated)</label>
                  <input
                    type="text"
                    value={manualForm.topics.join(', ')}
                    onChange={(e) => setManualForm({...manualForm, topics: e.target.value.split(',').map(t => t.trim()).filter(Boolean)})}
                    placeholder="AI, Productivity, Career"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 uppercase tracking-wide">Read Time (min)</label>
                  <input
                    type="number"
                    value={manualForm.read_time || ''}
                    onChange={(e) => setManualForm({...manualForm, read_time: parseInt(e.target.value) || null})}
                    placeholder="10"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg mt-1 focus:outline-none focus:ring-2 focus:ring-orange-500"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={handleManualSave}
                  disabled={loading || !manualForm.title.trim() || !manualForm.url.trim()}
                  className="px-6 py-2.5 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Saving...' : 'Save Article'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Articles List */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">All Articles ({articles.length})</h2>
          
          <div className="space-y-3">
            {articles.map((article) => (
              <div 
                key={article.id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div className="flex-1 min-w-0">
                  <a 
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-gray-900 hover:text-orange-600 truncate block"
                  >
                    {article.title}
                  </a>
                  <div className="text-sm text-gray-500 flex items-center gap-2 mt-1">
                    <span>{article.source}</span>
                    {article.read_time && (
                      <>
                        <span>·</span>
                        <span>{article.read_time} min</span>
                      </>
                    )}
                    <span>·</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      article.source_type === 'AI Suggested' 
                        ? 'bg-purple-100 text-purple-700' 
                        : 'bg-gray-200 text-gray-600'
                    }`}>
                      {article.source_type}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(article.id, article.title)}
                  className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg ml-3"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
            
            {articles.length === 0 && (
              <p className="text-gray-500 text-center py-8">No articles yet. Add your first one above!</p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

export default AdminPage
