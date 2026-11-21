import React from "react";

const INLINE_PATTERN = /(\*\*[^*]+?\*\*|__[^_]+?__|~~[^~]+?~~|`[^`]+`|\*[^*\n]+?\*|_[^_\n]+?_|\[[^\]]+\]\([^)]+\))/g;

function renderInline(text, keyPrefix) {
  const output = [];
  let cursor = 0;
  let match;
  let index = 0;

  while ((match = INLINE_PATTERN.exec(text)) !== null) {
    if (match.index > cursor) output.push(text.slice(cursor, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;

    if (token.startsWith("**") || token.startsWith("__")) {
      output.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("~~")) {
      output.push(<del key={key}>{token.slice(2, -2)}</del>);
    } else if (token.startsWith("`")) {
      output.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("[")) {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = link?.[2]?.trim();
      if (link && /^https?:\/\//i.test(href)) {
        output.push(
          <a key={key} href={href} target="_blank" rel="noreferrer noopener">
            {link[1]}
          </a>,
        );
      } else {
        output.push(token);
      }
    } else {
      output.push(<em key={key}>{token.slice(1, -1)}</em>);
    }

    cursor = match.index + token.length;
  }

  if (cursor < text.length) output.push(text.slice(cursor));
  return output;
}

function isBlockStart(line) {
  return /^\s*(?:#{1,6}\s|```|>\s?|[-*+]\s+|\d+\.\s+|(?:---+|___+|\*\*\*+)\s*$)/.test(line);
}

export default function MarkdownContent({ content }) {
  const lines = String(content ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const key = `block-${blocks.length}`;
    const fence = line.match(/^\s*```([\w-]*)\s*$/);
    if (fence) {
      index += 1;
      const codeLines = [];
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(
        <pre key={key}>
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const Tag = heading[1].length <= 2 ? "h3" : "h4";
      blocks.push(<Tag key={key}>{renderInline(heading[2], key)}</Tag>);
      index += 1;
      continue;
    }

    if (/^\s*(?:---+|___+|\*\*\*+)\s*$/.test(line)) {
      blocks.push(<hr key={key} />);
      index += 1;
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(
        <blockquote key={key}>
          {quoteLines.map((quoteLine, quoteIndex) => (
            <p key={`${key}-${quoteIndex}`}>{renderInline(quoteLine, `${key}-${quoteIndex}`)}</p>
          ))}
        </blockquote>,
      );
      continue;
    }

    const unordered = /^\s*[-*+]\s+/.test(line);
    const ordered = /^\s*\d+\.\s+/.test(line);
    if (unordered || ordered) {
      const items = [];
      while (index < lines.length) {
        const itemMatch = unordered
          ? lines[index].match(/^\s*[-*+]\s+(.+)$/)
          : lines[index].match(/^\s*\d+\.\s+(.+)$/);
        if (!itemMatch) break;
        items.push(itemMatch[1]);
        index += 1;
      }
      const List = unordered ? "ul" : "ol";
      blocks.push(
        <List key={key}>
          {items.map((item, itemIndex) => (
            <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
          ))}
        </List>,
      );
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={key}>{renderInline(paragraph.join(" "), key)}</p>);
  }

  return <div className="markdown-content">{blocks}</div>;
}
