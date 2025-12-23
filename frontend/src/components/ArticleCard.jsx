import React from 'react'

function ArticleCard({ article, onDismiss, onSave, isSaved, viewMode = 'cards' }) {
  const { title, url, source, author, read_time, topics, summary } = article

  // Single view - larger, centered card
  if (viewMode === 'single') {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 max-w-2xl mx-auto">
        {/* Source & Dismiss */}
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm font-medium text-gray-500">{source}</span>
          <button
            onClick={() => onDismiss(article.id)}
            className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="Don't show again"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Title */}
        <h2 className="text-2xl font-bold text-gray-900 mb-3 leading-tight">
          {title}
        </h2>

        {/* Summary */}
        <p className="text-gray-600 mb-5 leading-relaxed">
          {summary}
        </p>

        {/* Topics */}
        <div className="flex flex-wrap gap-2 mb-5">
          {topics.slice(0, 4).map((topic) => (
            <span
              key={topic}
              className="px-3 py-1 text-sm font-medium text-gray-600 bg-gray-100 rounded-full"
            >
              {topic}
            </span>
          ))}
        </div>

        {/* Meta */}
        <div className="flex items-center gap-3 text-sm text-gray-500 mb-6">
          {author && author !== source && (
            <>
              <span>{author}</span>
              <span>·</span>
            </>
          )}
          <div className="flex items-center gap-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{read_time} min read</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={() => onSave(article)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-colors ${
              isSaved 
                ? 'bg-gray-900 text-white' 
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <svg className="w-5 h-5" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
            </svg>
            {isSaved ? 'Saved' : 'Save'}
          </button>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 text-center py-2.5 px-6 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 transition-colors flex items-center justify-center gap-2"
          >
            Read Article
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </a>
        </div>
      </div>
    )
  }

  // Cards view - compact grid card
  return (
    <div className="article-card bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex flex-col h-full hover:shadow-md transition-shadow">
      {/* Source & Dismiss */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-500">{source}</span>
        <button
          onClick={() => onDismiss(article.id)}
          className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
          title="Don't show again"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Title */}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="group"
      >
        <h2 className="text-lg font-semibold text-gray-900 group-hover:text-orange-600 transition-colors mb-2 line-clamp-2 leading-snug">
          {title}
        </h2>
      </a>

      {/* Summary */}
      <p className="text-sm text-gray-600 mb-4 line-clamp-3 flex-grow leading-relaxed">
        {summary}
      </p>

      {/* Topics */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {topics.slice(0, 3).map((topic) => (
          <span
            key={topic}
            className="px-2 py-0.5 text-xs font-medium text-gray-500 bg-gray-100 rounded-full"
          >
            {topic}
          </span>
        ))}
      </div>

      {/* Meta */}
      <div className="flex items-center text-sm text-gray-500 mb-4 pt-3 border-t border-gray-100">
        {author && author !== source && (
          <>
            <span className="truncate">{author}</span>
            <span className="mx-2">·</span>
          </>
        )}
        <div className="flex items-center gap-1">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{read_time} min</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={() => onSave(article)}
          className={`p-2 rounded-lg transition-colors ${
            isSaved 
              ? 'bg-gray-900 text-white' 
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
          title={isSaved ? 'Saved' : 'Save'}
        >
          <svg className="w-5 h-5" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
          </svg>
        </button>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-center py-2 px-4 bg-orange-500 text-white text-sm font-medium rounded-lg hover:bg-orange-600 transition-colors"
        >
          Read
        </a>
      </div>
    </div>
  )
}

export default ArticleCard
