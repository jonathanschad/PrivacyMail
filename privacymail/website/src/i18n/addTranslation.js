const fs = require("fs");
const readline = require("readline");
const prettier = require("prettier");
const prettierConfig = require("../../package.json").prettier;
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

/**
 * This is a Script to add new Translations in alphabetical to the Website
 * execute this script by typing 'node addTranslation' and follow the instructions
 */

function orderKeys(obj) {
    return Object.keys(obj)
        .sort(function(a, b) {
            return a.toLowerCase().localeCompare(b.toLowerCase());
        })
        .reduce(
            (acc, key) => ({
                ...acc,
                [key]: obj[key]
            }),
            {}
        );
}
//prettier.getFileInfo("./de.json").then(res=> console.log(res));

const de = JSON.parse(fs.readFileSync("./de.json"));
const en = JSON.parse(fs.readFileSync("./en.json"));
rl.question("Enter new Translation key: ", key => {
    if (de[key] || en[key]) {
        console.error("The key you entered already exists");
        rl.close();
    } else {
        rl.question("Enter German Translation: ", german => {
            rl.question("Enter English Translation: ", english => {
                console.log("\n", "\nKey: ", key, "\nGerman: ", german, "\nEnglish: ", english);
                rl.question("Is you Input correct? (y/n): ", confirm => {
                    if (confirm === "y" || confirm === "j" || confirm === "Y" || confirm === "J") {
                        de[key] = german;
                        en[key] = english;

                        fs.writeFileSync(
                            "./de.json",
                            prettier.format(JSON.stringify(orderKeys(de)), {
                                semi: false,
                                parser: "json",
                                ...prettierConfig
                            })
                        );
                        fs.writeFileSync(
                            "./en.json",
                            prettier.format(JSON.stringify(orderKeys(en)), {
                                semi: false,
                                parser: "json",
                                ...prettierConfig
                            })
                        );
                    }
                    rl.close();
                });
            });
        });
    }
});

//fs.writeFileSync(process.argv[2], JSON.stringify(result));
