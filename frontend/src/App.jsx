import React, { useState, useEffect, useCallback } from 'react'
import ArticleCard from './components/ArticleCard'

// Use environment variable for API URL, fallback to proxy in dev
const API_BASE = import.meta.env.VITE_API_URL || '/api'

function App() {
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [shuffling, setShuffling] = useState(false)

  const fetchArticles = useCallback(async () => {
    try {
      setShuffling(true)
      const response = await fetch(`${API_BASE}/articles/random?count=4`)
      if (!response.ok) throw new Error('Failed to fetch articles')
      const data = await response.json()
      setArticles(data.articles)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setShuffling(false)
    }
  }, [])

  useEffect(() => {
    fetchArticles()
  }, [fetchArticles])

  const handleDismiss = async (articleId) => {
    try {
      await fetch(`${API_BASE}/articles/${articleId}/dismiss`, { method: 'POST' })
      // Fetch a replacement article
      const response = await fetch(`${API_BASE}/articles/random?count=1`)
      const data = await response.json()
      if (data.articles.length > 0) {
        setArticles((prev) =>
          prev.map((a) => (a.id === articleId ? data.articles[0] : a))
        )
      }
    } catch (err) {
      console.error('Failed to dismiss article:', err)
    }
  }

  const handleShuffle = () => {
    fetchArticles()
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">Loading your reading list...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={fetchArticles}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800"
          >
            Try Again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <span>🐰</span>
                <span>ReadRabbit</span>
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                Go down the rabbit hole. Read something great.
              </p>
            </div>
            <button
              onClick={handleShuffle}
              disabled={shuffling}
              className="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              <svg
                className={`w-5 h-5 ${shuffling ? 'animate-spin' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span>{shuffling ? 'Shuffling...' : 'Shuffle'}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {articles.map((article) => (
            <ArticleCard
              key={article.id}
              article={article}
              onDismiss={handleDismiss}
            />
          ))}
        </div>

        {/* Footer hint */}
        <div className="text-center mt-12 text-sm text-gray-400">
          Click an article to read, or shuffle for new picks
        </div>
      </main>
    </div>
  )
}

export default App
