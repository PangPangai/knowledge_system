'use client';

import { useState } from 'react';
import { marked } from 'marked';

interface ExportButtonsProps {
    question: string;
    answer: string;
    answerId: string;
}

// Helper to sanitize filename
const sanitizeFilename = (text: string): string => {
    if (!text) return 'untitled';
    return text
        .replace(/[\\/:*?"<>|]/g, '')
        .replace(/\s+/g, '_')
        .slice(0, 20);
};

// Comprehensive inline CSS for PDF rendering
// mimic GitHub Markdown style closely
const PDF_STYLES = `
    <style>
        /* Base Reset */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
            color: #24292f; 
            line-height: 1.5; 
            font-size: 14px; 
            background: #ffffff; 
            padding: 40px;
        }

        /* Page Breaks - Critical for PDF */
        h1, h2, h3, h4, h5, h6, p, li, pre, blockquote, table, img {
            page-break-inside: avoid;
            break-inside: avoid;
        }

        /* ---------------------------------------------------------
         *  GitHub Markdown Style Mimic
         * --------------------------------------------------------- */
        
        /* Headers */
        h1, h2, h3, h4, h5, h6 {
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
            color: #24292f;
        }
        
        h1 { font-size: 2em; padding-bottom: 0.3em; border-bottom: 1px solid #d0d7de; }
        h2 { font-size: 1.5em; padding-bottom: 0.3em; border-bottom: 1px solid #d0d7de; }
        h3 { font-size: 1.25em; }
        h4 { font-size: 1em; }
        h5 { font-size: 0.875em; }
        h6 { font-size: 0.85em; color: #57606a; }

        /* Text */
        p { margin-top: 0; margin-bottom: 16px; }
        strong { font-weight: 600; }
        em { font-style: italic; }
        
        /* Links */
        a { color: #0969da; text-decoration: none; }
        a:hover { text-decoration: underline; }

        /* Blockquotes */
        blockquote {
            margin: 0 0 16px;
            padding: 0 1em;
            color: #57606a;
            border-left: 0.25em solid #d0d7de;
        }

        /* Lists */
        ul, ol {
            margin-top: 0;
            margin-bottom: 16px;
            padding-left: 2em;
        }
        li { margin-top: 0.25em; }
        li + li { margin-top: 0.25em; }
        
        /* Task lists */
        li input[type="checkbox"] { margin: 0 0.2em 0.25em -1.6em; vertical-align: middle; }

        /* Code Inline */
        code {
            padding: 0.2em 0.4em;
            margin: 0;
            font-size: 85%;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
            background-color: #afb8c133; 
            border-radius: 6px;
            color: #24292f;
        }

        /* Code Blocks */
        pre {
            padding: 16px;
            overflow: auto;
            font-size: 85%;
            line-height: 1.45;
            background-color: #f6f8fa;
            border-radius: 6px;
            margin-bottom: 16px;
            white-space: pre-wrap;
            word-wrap: break-word;
            overflow-wrap: break-word; /* Important for PDF wrapping */
        }
        
        pre code {
            display: inline;
            padding: 0;
            margin: 0;
            overflow: visible;
            line-height: inherit;
            word-wrap: normal;
            background-color: transparent;
            border: 0;
            color: #24292f;
            white-space: pre; /* Inner code maintains spacing */
        }

        /* Tables */
        table {
            border-spacing: 0;
            border-collapse: collapse;
            display: block;
            width: max-content;
            max-width: 100%;
            overflow: auto;
            margin-bottom: 16px;
        }
        
        table th, table td {
            padding: 6px 13px;
            border: 1px solid #d0d7de;
        }
        
        table th {
            font-weight: 600;
            background-color: #f6f8fa;
        }
        
        table tr {
            background-color: #ffffff;
            border-top: 1px solid #d8dee4;
        }
        
        table tr:nth-child(2n) {
            background-color: #f6f8fa;
        }

        /* Images */
        img {
            max-width: 100%;
            box-sizing: content-box;
            background-color: #ffffff;
        }

        /* Horizontal Rule */
        hr {
            height: 0.25em;
            padding: 0;
            margin: 24px 0;
            background-color: #d0d7de;
            border: 0;
        }

        /* Helper Classes for Header metadata */
        .meta-info {
            font-size: 12px;
            color: #57606a;
            margin-bottom: 32px;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
            border-bottom: 1px solid #d0d7de;
            padding-bottom: 8px;
        }
    </style>
`;

export default function ExportButtons({ question, answer, answerId }: ExportButtonsProps) {
    const [isExporting, setIsExporting] = useState(false);

    const getBaseFilename = () => {
        const now = new Date();
        const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
        const title = sanitizeFilename(question);
        return `${title}_${timestamp}`;
    };

    const handleExportMarkdown = () => {
        const filename = `${getBaseFilename()}.md`;
        const content = `**问题**：\n${question}\n\n**回答**：\n${answer}`;

        const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const handleExportPDF = async () => {
        if (isExporting) return;
        setIsExporting(true);

        try {
            // @ts-ignore
            const html2pdf = (await import('html2pdf.js')).default;

            // 1. Convert Markdown to HTML
            // Using marked with default settings matches standard markdown parsing
            const answerHtml = marked.parse(answer) as string;

            // 2. Build complete HTML document
            const fullHtml = `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Export</title>
                </head>
                <body>
                    ${PDF_STYLES}
                    <div class="meta-info">
                        Generated on ${new Date().toLocaleString()}
                    </div>

                    <h1>${question.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</h1>
                    
                    <div class="markdown-body">
                        ${answerHtml}
                    </div>
                </body>
                </html>
            `;

            // 3. Create a hidden iframe
            const iframe = document.createElement('iframe');
            iframe.style.position = 'fixed';
            iframe.style.left = '-10000px';
            iframe.style.top = '0';
            iframe.style.width = '800px'; // A4 width approx
            iframe.style.height = '100%';
            iframe.style.border = 'none';
            iframe.style.visibility = 'hidden';

            document.body.appendChild(iframe);

            // 4. Write content to iframe
            const doc = iframe.contentDocument || iframe.contentWindow?.document;
            if (doc) {
                doc.open();
                doc.write(fullHtml);
                doc.close();

                // Wait for content (especially images/fonts) to layout
                await new Promise(resolve => setTimeout(resolve, 500));

                const opt = {
                    margin: [15, 15, 15, 15] as [number, number, number, number],
                    filename: `${getBaseFilename()}.pdf`,
                    image: { type: 'jpeg' as const, quality: 0.98 },
                    html2canvas: {
                        scale: 2,
                        useCORS: true,
                        logging: false,
                        windowWidth: 800
                    },
                    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' as const },
                    pagebreak: { mode: ['css', 'legacy'] }
                };

                // 5. Generate PDF from iframe body
                await html2pdf().set(opt).from(doc.body).save();
            }

            // Store ref to cleanup
            (window as any).__exportIframe = iframe;

        } catch (error) {
            console.error('PDF Export failed:', error);
            alert('导出 PDF 失败：' + (error instanceof Error ? error.message : String(error)));
        } finally {
            // Cleanup
            const iframe = (window as any).__exportIframe;
            if (iframe && document.body.contains(iframe)) {
                document.body.removeChild(iframe);
                (window as any).__exportIframe = null;
            }
            setIsExporting(false);
        }
    };

    return (
        <div className="flex gap-2 mt-4">
            <button
                onClick={handleExportMarkdown}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-[var(--accent-primary)] hover:bg-gray-100 rounded-md transition-colors"
                title="导出为 Markdown"
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Markdown</span>
            </button>
            <button
                onClick={handleExportPDF}
                disabled={isExporting}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-[var(--accent-primary)] hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
                title="导出为 PDF"
            >
                {isExporting ? (
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                )}
                <span>PDF</span>
            </button>
        </div>
    );
}
