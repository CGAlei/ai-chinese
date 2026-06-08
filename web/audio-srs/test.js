const fs = require('fs');

const data = JSON.parse(fs.readFileSync('/home/alex/Ai-chinese/AudioSRS/opencodeversion/data/vocabulary.json', 'utf8'));

let queue = data.filter(w => w.reps === 0 && !w.hidden);
queue.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));

console.log("Top 5 newest words:");
for (let i = 0; i < 5; i++) {
    console.log(queue[i].id, queue[i].createdAt);
}
